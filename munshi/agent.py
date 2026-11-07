"""The Munshi agent: controls -> recall -> decide -> guardrails."""

import json
import logging
import time

from . import rules
from .llm import LLMError, chat_json

log = logging.getLogger("munshi.agent")

ACTIONS = ["APPROVE", "APPROVE_PARTIAL", "REQUEST_VENDOR_CORRECTION", "ROUTE_FOR_APPROVAL", "HOLD"]
PAYMENT_BASIS = ["FULL", "EXCLUDE_GST", "EXCLUDE_DISPUTED", "NONE"]

# Who owns an exception when memory has nothing to say.
DEFAULT_OWNER = {
    "PRICE_VARIANCE": ("Meera Iyer", "Head of Procurement"),
    "UNPLANNED_CHARGE": ("Arjun Rao", "Logistics Manager"),
    "GSTR2B_MISSING": ("Kavya Menon", "Financial Controller"),
    "TDS_UNCLASSIFIED": ("Kavya Menon", "Financial Controller"),
    "TDS_SECTION_CONFLICT": ("Kavya Menon", "Financial Controller"),
    "QTY_MISMATCH": ("Ravi Kumar", "AP Executive"),
    "DUPLICATE_SUSPECTED": ("Ravi Kumar", "AP Executive"),
    "GSTIN_INVALID": ("Kavya Menon", "Financial Controller"),
    "DUPLICATE_EXACT": ("Ravi Kumar", "AP Executive"),
    "TAX_TYPE_MISMATCH": ("Kavya Menon", "Financial Controller"),
}

SYSTEM = """You are Munshi, an accounts payable exception agent for Kaveri Precision Components Pvt Ltd (Bengaluru, India).
Deterministic controls have already run. Your job is to decide what happens to this invoice.

Allowed actions:
- APPROVE: pay in full.
- APPROVE_PARTIAL: pay part now, hold the rest (e.g. hold GST until GSTR-2B reflects, or pay only received quantity).
- REQUEST_VENDOR_CORRECTION: do not pay; send the vendor a correction request (draft the email).
- ROUTE_FOR_APPROVAL: a named person with authority must decide.
- HOLD: stop; a hard control failed.

Payment basis (the system computes rupee amounts from this, never do arithmetic yourself):
FULL | EXCLUDE_GST (hold the GST component) | EXCLUDE_DISPUTED (deduct the disputed excess / over-billed / unapproved charge and its GST) | NONE.

Rules:
1. Use ONLY the memories provided. Every reasoning point that relies on a memory must cite its id in memory_ids.
2. A tolerance or standing instruction applies only to the vendor and exception it was set for. A rule learned for one vendor does NOT transfer to another vendor.
3. If a learned threshold exists but this invoice exceeds it, follow the instruction for that case (e.g. route to the named person, or push back).
4. If no memory covers an exception, the safe default is ROUTE_FOR_APPROVAL to the default owner given.
5. Hard controls (hard=true) always mean HOLD, whatever memory says.
6. For MSME vendors, mention the statutory pay-by date.
7. If you draft a vendor email, be specific and polite, cite contract clauses or facts from memory, sign as "Accounts Payable, Kaveri Precision Components".

Return a JSON object with exactly these keys:
{"action": one of the actions, "payment_basis": one of the bases,
 "route_to": {"name": str, "role": str} or null,
 "headline": one sentence a CFO would read,
 "reasoning": [{"point": str, "memory_ids": [str]}],
 "learned_rule_applied": str or null  (the standing rule from memory you relied on, quoted briefly),
 "vendor_email": {"subject": str, "body": str} or null,
 "confidence": number 0..1}"""


def _invoice_view(inv, vendor, findings):
    return {
        "invoice": {k: inv[k] for k in ("invoice_number", "invoice_date", "received_date", "po_number",
                                        "taxable_value", "taxes", "total", "tds_section_on_invoice")},
        "lines": inv["lines"],
        "extra_charges": inv["extra_charges"],
        "vendor": {k: vendor[k] for k in ("id", "name", "city", "gstin", "msme", "terms_days", "category", "tds_section")},
        "control_findings": [f.to_dict() for f in findings],
        "default_owners": {f.code: DEFAULT_OWNER.get(f.code) for f in findings if f.code in DEFAULT_OWNER},
    }


def _amounts(inv, findings, basis):
    total, tax = inv["total"], sum(inv["taxes"].values())
    if basis == "FULL":
        held = 0.0
    elif basis == "EXCLUDE_GST":
        held = tax
    elif basis == "EXCLUDE_DISPUTED":
        disputed = sum(f.amount_at_risk for f in findings
                       if f.code in ("PRICE_VARIANCE", "QTY_MISMATCH", "UNPLANNED_CHARGE"))
        held = disputed * (1 + tax / inv["taxable_value"])  # disputed value plus its GST
    else:
        held = total
    held = round(min(held, total), 2)
    return round(total - held, 2), held


def _fallback(findings, reason):
    hard = any(f.hard for f in findings)
    owner = next((DEFAULT_OWNER[f.code] for f in findings if f.code in DEFAULT_OWNER), ("Kavya Menon", "Financial Controller"))
    return {
        "action": "HOLD" if hard else "ROUTE_FOR_APPROVAL",
        "payment_basis": "NONE",
        "route_to": {"name": owner[0], "role": owner[1]},
        "headline": f"Escalated for human review ({reason}).",
        "reasoning": [{"point": f"{f.title}: {f.detail}", "memory_ids": []} for f in findings if f.severity != "info"],
        "learned_rule_applied": None,
        "vendor_email": None,
        "confidence": 0.3,
        "degraded": True,
    }


def _sanitise(d: dict, memories: list[dict], findings) -> dict:
    valid_ids = {m["id"] for m in memories}
    d["action"] = d.get("action") if d.get("action") in ACTIONS else "ROUTE_FOR_APPROVAL"
    d["payment_basis"] = d.get("payment_basis") if d.get("payment_basis") in PAYMENT_BASIS else "NONE"
    reasoning, dropped = [], 0
    for r in d.get("reasoning") or []:
        if not isinstance(r, dict):
            r = {"point": str(r), "memory_ids": []}
        ids = [str(i)[:8] for i in r.get("memory_ids") or []]
        dropped += sum(1 for i in ids if i not in valid_ids)
        reasoning.append({"point": str(r.get("point", "")), "memory_ids": [i for i in ids if i in valid_ids]})
    d["reasoning"] = reasoning
    d["dropped_citations"] = dropped
    try:
        d["confidence"] = max(0.0, min(1.0, float(d.get("confidence", 0.5))))
    except (TypeError, ValueError):
        d["confidence"] = 0.5
    if d["action"] in ("ROUTE_FOR_APPROVAL", "HOLD") and not d.get("route_to"):
        code = next((f.code for f in findings if f.code in DEFAULT_OWNER), None)
        if code:
            d["route_to"] = {"name": DEFAULT_OWNER[code][0], "role": DEFAULT_OWNER[code][1]}
    if d["action"] in ("APPROVE", "APPROVE_PARTIAL"):
        d["route_to"] = None
    return d


class Agent:
    def __init__(self, book: dict, memory):
        self.book = book
        self.controls = rules.Controls(book)
        self.memory = memory
        self.vendors = {v["id"]: v for v in book["vendors"]}

    async def analyse(self, inv: dict, use_memory: bool = True) -> dict:
        t0 = time.perf_counter()
        vendor = self.vendors[inv["vendor_id"]]
        findings = self.controls.run(inv)
        summary = rules.summarise(findings)
        timings = {}

        memories, memory_error = [], None
        if use_memory:
            t = time.perf_counter()
            try:
                memories = await self.memory.recall_for_invoice(inv, vendor, summary["codes"])
            except Exception as e:
                log.exception("recall failed")
                memory_error = str(e)
            timings["recall_ms"] = int((time.perf_counter() - t) * 1000)

        if summary["clean"]:
            decision = {
                "action": "APPROVE", "payment_basis": "FULL", "route_to": None,
                "headline": "All controls passed: three-way match, GSTIN, GSTR-2B, tax type, duplicates.",
                "reasoning": [{"point": f.title, "memory_ids": []} for f in findings],
                "learned_rule_applied": None, "vendor_email": None, "confidence": 0.97, "straight_through": True,
            }
        else:
            prompt = json.dumps(_invoice_view(inv, vendor, findings), ensure_ascii=False, indent=1)
            if use_memory:
                mem_txt = "\n".join(f"[{m['id']}] ({m['date']}, {m['scope']}) {m['text']}" for m in memories) or "(no relevant memories)"
            else:
                mem_txt = "(memory disabled: you have no history with this vendor or these exceptions)"
            t = time.perf_counter()
            try:
                raw = await chat_json(SYSTEM, f"INVOICE AND CONTROL RESULTS:\n{prompt}\n\nMEMORIES FROM HINDSIGHT:\n{mem_txt}")
                decision = _sanitise(raw, memories, findings)
            except LLMError as e:
                decision = _fallback(findings, f"reasoning model unavailable: {e}")
            timings["llm_ms"] = int((time.perf_counter() - t) * 1000)

        if summary["hard_stop"] and decision["action"] != "HOLD":
            decision["guardrail"] = f"Model proposed {decision['action']}; forced to HOLD because a hard control failed."
            decision["action"], decision["payment_basis"] = "HOLD", "NONE"
            decision["route_to"] = decision.get("route_to") or {"name": "Kavya Menon", "role": "Financial Controller"}

        payable, held = _amounts(inv, findings, decision["payment_basis"])
        if decision["action"] in ("REQUEST_VENDOR_CORRECTION", "ROUTE_FOR_APPROVAL", "HOLD"):
            payable, held = 0.0, inv["total"]
        timings["total_ms"] = int((time.perf_counter() - t0) * 1000)
        return {
            "invoice_id": inv["id"],
            "memory_on": use_memory,
            "findings": [f.to_dict() for f in findings],
            "summary": summary,
            "memories": memories,
            "memory_error": memory_error,
            "decision": decision,
            "payable": payable,
            "held": held,
            "needs_senior": decision["action"] in ("ROUTE_FOR_APPROVAL", "HOLD"),
            "timings": timings,
        }
