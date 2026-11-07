import asyncio

import pytest

from munshi import agent as agent_mod
from munshi import gstin, rules, store
from munshi.agent import Agent

BOOK = store.load_book()
INV = {i["id"]: i for i in BOOK["invoices"]}
CONTROLS = rules.Controls(BOOK)


def codes(inv_id):
    return rules.summarise(CONTROLS.run(INV[inv_id]))["codes"]


def test_gstin_checksum():
    assert gstin.validate("27AAPFU0939F1ZV")[0]
    assert not gstin.validate("27AAPFU0939F1ZA")[0]
    assert not gstin.validate("NOTAGSTIN")[0]


@pytest.mark.parametrize("inv_id,expected", [
    ("INV-1101", []),
    ("INV-1102", ["PRICE_VARIANCE"]),
    ("INV-1103", ["UNPLANNED_CHARGE"]),
    ("INV-1104", ["GSTR2B_MISSING"]),
    ("INV-1105", ["DUPLICATE_SUSPECTED"]),
    ("INV-1107", ["TDS_UNCLASSIFIED"]),
    ("INV-1108", ["PRICE_VARIANCE"]),
    ("INV-1109", ["QTY_MISMATCH"]),
])
def test_controls(inv_id, expected):
    assert codes(inv_id) == expected


def test_invalid_gstin_is_hard_stop():
    s = rules.summarise(CONTROLS.run(INV["INV-1106"]))
    assert "GSTIN_INVALID" in s["codes"] and s["hard_stop"]


def test_msme_due_date_is_capped_at_45_days():
    f = next(f for f in CONTROLS.run(INV["INV-1105"]) if f.code == "MSME_45_DAY")
    assert f.facts["pay_by"] == "2026-12-20"  # received 5 Nov + 45 days, though terms are 60


class FakeMemory:
    def __init__(self, memories=None):
        self.memories = memories or []

    async def recall_for_invoice(self, inv, vendor, codes):
        return self.memories


def run(inv_id, monkeypatch, llm_output, memories=None, use_memory=True):
    async def fake_chat(system, user, **kw):
        if isinstance(llm_output, Exception):
            raise llm_output
        return dict(llm_output)
    monkeypatch.setattr(agent_mod, "chat_json", fake_chat)
    return asyncio.run(Agent(BOOK, FakeMemory(memories)).analyse(INV[inv_id], use_memory))


def test_guardrail_overrides_model_on_hard_control(monkeypatch):
    a = run("INV-1106", monkeypatch, {"action": "APPROVE", "payment_basis": "FULL", "headline": "ok", "confidence": 0.9})
    assert a["decision"]["action"] == "HOLD" and a["payable"] == 0 and "guardrail" in a["decision"]


def test_hallucinated_memory_citations_are_dropped(monkeypatch):
    mems = [{"id": "abc12345", "text": "SBP escalation up to 2.5%", "date": "2026-09-03", "scope": "vendor"}]
    a = run("INV-1102", monkeypatch, {
        "action": "APPROVE", "payment_basis": "FULL", "headline": "within tolerance",
        "reasoning": [{"point": "clause 7.2", "memory_ids": ["abc12345", "deadbeef"]}], "confidence": 0.9,
    }, mems)
    assert a["decision"]["reasoning"][0]["memory_ids"] == ["abc12345"]
    assert a["decision"]["dropped_citations"] == 1
    assert a["payable"] == INV["INV-1102"]["total"]


def test_partial_payment_holds_gst(monkeypatch):
    a = run("INV-1104", monkeypatch, {"action": "APPROVE_PARTIAL", "payment_basis": "EXCLUDE_GST", "headline": "hold GST"})
    inv = INV["INV-1104"]
    assert a["held"] == round(sum(inv["taxes"].values()), 2)
    assert a["payable"] == pytest.approx(inv["taxable_value"], abs=0.02)


def test_llm_failure_falls_back_to_escalation(monkeypatch):
    a = run("INV-1103", monkeypatch, agent_mod.LLMError("rate limited"))
    assert a["decision"]["action"] == "ROUTE_FOR_APPROVAL"
    assert a["decision"]["route_to"]["name"] == "Arjun Rao"
    assert a["needs_senior"]


def test_clean_invoice_goes_straight_through(monkeypatch):
    a = run("INV-1101", monkeypatch, RuntimeError("LLM must not be called"))
    assert a["decision"]["action"] == "APPROVE" and a["decision"].get("straight_through")
