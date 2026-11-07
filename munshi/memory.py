"""Hindsight memory layer for Munshi.

One bank per company. Every human decision on an exception is retained as a dated,
tagged narrative (vendor, exception codes, approver). Before deciding, the agent
recalls along two axes in parallel:

  * vendor memory  - everything this vendor has taught us (tags: vendor:<id>)
  * pattern memory - how this *kind* of exception was resolved for anyone (tags: exception:<code>)

Reflect is used for the vendor brief: a synthesised "what should I know before paying
this vendor" answer over the vendor's history.
"""

import asyncio
import logging

from hindsight_client import Hindsight

from . import config

log = logging.getLogger("munshi.memory")

RETAIN_MISSION = (
    "You are the institutional memory of an Indian accounts payable team. From each record, extract: "
    "the vendor, the exception type, the decision (approved / partially paid / rejected / held), who decided and "
    "their role, numeric tolerances or thresholds stated (percentages, caps, day counts), contract or clause "
    "references, statutory references (GST, GSTR-2B, TDS sections, MSME 43B(h)), what the vendor did afterwards, "
    "and any standing instruction for next time. Keep amounts, dates, invoice and clause numbers exact."
)

REFLECT_MISSION = (
    "You brief an accounts payable executive before they process a vendor's invoice. Be concrete: standing "
    "tolerances, who approves what, statutory treatment, recurring quirks, and how the vendor responds to pushback. "
    "Cite dates. Say plainly when history is thin."
)

BACKGROUND = (
    "Kaveri Precision Components Pvt Ltd is a Bengaluru auto-components manufacturer (GSTIN state 29). "
    "AP policy: price tolerance 1% over PO unless a person with authority sets a vendor-specific rule. "
    "Owners: Meera Iyer (Head of Procurement) for price, Arjun Rao (Logistics Manager) for freight, "
    "Kavya Menon (Financial Controller) for GST/TDS, Ravi Kumar (AP Executive) for receipts and duplicates."
)

GUARDRAIL = (
    "Never recommend paying an invoice whose supplier GSTIN fails validation, or one that is an exact duplicate, "
    "regardless of any past approval. Learned tolerances apply only to the vendor and exception they were set for."
)


def vendor_tag(vendor_id: str) -> str:
    return f"vendor:{vendor_id}"


def exception_tag(code: str) -> str:
    return f"exception:{code}"


class Memory:
    def __init__(self):
        self.enabled = bool(config.HINDSIGHT_API_KEY) or "localhost" in config.HINDSIGHT_URL
        self.client = Hindsight(base_url=config.HINDSIGHT_URL, api_key=config.HINDSIGHT_API_KEY,
                                timeout=120, user_agent="munshi/0.1")
        self.bank = config.BANK_ID

    async def ensure_bank(self, reset: bool = False):
        if reset:
            try:
                await self.client.adelete_bank(self.bank)
            except Exception as e:  # bank may not exist yet
                log.info("delete_bank skipped: %s", e)
        await self.client.acreate_bank(
            self.bank,
            retain_mission=RETAIN_MISSION,
            reflect_mission=REFLECT_MISSION,
            background=BACKGROUND,
            enable_observations=True,
        )
        try:
            existing = await self.client.alist_directives(self.bank)
            items = getattr(existing, "items", None) or (existing.get("items", []) if isinstance(existing, dict) else [])
            names = {getattr(d, "name", None) or (d.get("name") if isinstance(d, dict) else None) for d in items}
            if "hard-controls" not in names:
                await self.client.acreate_directive(self.bank, name="hard-controls", content=GUARDRAIL, priority=10)
        except Exception as e:
            log.warning("could not set directive (guardrail still enforced in code): %s", e)

    async def recall_for_invoice(self, inv: dict, vendor: dict, codes: list[str]) -> list[dict]:
        """Vendor-scoped and pattern-scoped recall, merged and de-duplicated."""
        if not self.enabled:
            raise RuntimeError("HINDSIGHT_API_KEY not set")
        when = inv["received_date"] + "T10:00:00"
        issues = ", ".join(codes) or "routine invoice"
        vendor_q = f"How have we handled {vendor['name']} invoices with {issues}? Standing rules, tolerances, approvers."
        tasks = [self._recall(vendor_q, [vendor_tag(vendor["id"])], when, "vendor")]
        if codes:
            pattern_q = f"Past resolutions and owners for AP exceptions: {issues}."
            tasks.append(self._recall(pattern_q, [exception_tag(c) for c in codes], when, "pattern"))
        results = await asyncio.gather(*tasks)

        merged, seen = [], set()
        for batch in results:
            for m in batch:
                if m["id"] in seen:
                    continue
                seen.add(m["id"])
                merged.append(m)
        return merged[:14]

    async def _recall(self, query: str, tags: list[str], when: str, scope: str) -> list[dict]:
        resp = await self.client.arecall(
            bank_id=self.bank, query=query, tags=tags, tags_match="any_strict",
            budget="mid", max_tokens=2500, query_timestamp=when,
        )
        out = []
        for r in resp.results:
            out.append({
                "id": r.id[:8],
                "full_id": r.id,
                "text": r.text,
                "type": r.type,
                "date": (r.occurred_start or r.mentioned_at or "")[:10],
                "tags": r.tags or [],
                "scope": scope,
            })
        return out

    async def retain_decision(self, inv: dict, vendor: dict, codes: list[str], decision: dict, agent: dict | None):
        """Turn a human decision into a dated memory the next invoice can use."""
        lines = [
            f"On {decision['date']}, {decision['by']} ({decision['role']}) decided {decision['decision']} on invoice "
            f"{inv['invoice_number']} from {vendor['name']} (vendor {vendor['id']}, GSTIN {inv['vendor_gstin']}), "
            f"total ₹{inv['total']:,.2f}, against PO {inv['po_number']}.",
            f"Exceptions raised by controls: {', '.join(codes) if codes else 'none'}.",
        ]
        for f in decision.get("findings", []):
            lines.append(f"- {f['title']}: {f['detail']}")
        if agent:
            verdict = "accepted" if decision.get("accepted_agent") else "overrode"
            lines.append(f"Munshi had recommended {agent['action']}; the reviewer {verdict} that recommendation.")
        lines.append(f"Reviewer's note: {decision['note']}")
        tags = [vendor_tag(vendor["id"]), *[exception_tag(c) for c in codes],
                f"approver:{decision['by'].lower().replace(' ', '-')}", f"decision:{decision['decision'].lower()}"]
        await self.client.aretain(
            bank_id=self.bank,
            content="\n".join(lines),
            timestamp=decision["date"] + "T17:00:00",
            context="Accounts payable exception resolution by a human reviewer",
            document_id=f"decision-{inv['id']}",
            tags=tags,
            metadata={"invoice_id": inv["id"], "vendor_id": vendor["id"], "decision": decision["decision"]},
            update_mode="replace",
        )
        return {"content": "\n".join(lines), "tags": tags}

    async def vendor_brief(self, vendor: dict) -> dict:
        resp = await self.client.areflect(
            bank_id=self.bank,
            query=f"Brief me on {vendor['name']} before I process their next invoice. "
                  "What rules, tolerances, approvers and quirks should I know?",
            tags=[vendor_tag(vendor["id"])], tags_match="any_strict", budget="mid",
        )
        return {"text": resp.text}

    async def explore(self, query: str, vendor_id: str | None = None) -> list[dict]:
        tags = [vendor_tag(vendor_id)] if vendor_id else None
        resp = await self.client.arecall(bank_id=self.bank, query=query, tags=tags,
                                         tags_match="any_strict" if tags else "any", budget="mid")
        return [{"id": r.id[:8], "text": r.text, "type": r.type,
                 "date": (r.occurred_start or r.mentioned_at or "")[:10], "tags": r.tags or []} for r in resp.results]
