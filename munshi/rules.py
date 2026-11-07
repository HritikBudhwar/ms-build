"""Deterministic AP controls. These run before the agent and never depend on memory.

Each check returns Finding objects. A finding with hard=True is a control that memory
is not allowed to override (invalid GSTIN, exact duplicate): the agent can explain it,
but the final action is forced to HOLD.
"""

import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from . import gstin as gst


@dataclass
class Finding:
    code: str
    title: str
    detail: str
    severity: str  # "info" | "warning" | "critical"
    hard: bool = False
    amount_at_risk: float = 0.0
    facts: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


_REVISION_SUFFIX = re.compile(r"[-/ ]?(R|REV|REVISED)\d*$", re.I)


def _base_number(no: str) -> str:
    return _REVISION_SUFFIX.sub("", no.strip().upper())


def _inr(x: float) -> str:
    return f"₹{x:,.2f}"


class Controls:
    def __init__(self, book: dict):
        self.book = book
        self.buyer = book["buyer"]
        self.vendors = {v["id"]: v for v in book["vendors"]}
        self.pos = {p["po_number"]: p for p in book["purchase_orders"]}
        self.grns = {g["invoice_id"]: g for g in book["grns"]}
        self.gstr2b = {(r["supplier_gstin"], r["invoice_number"]) for r in book["gstr2b"]}

    def run(self, inv: dict) -> list[Finding]:
        vendor = self.vendors[inv["vendor_id"]]
        findings: list[Finding] = []
        findings += self._gstin(inv)
        findings += self._duplicate(inv)
        findings += self._price(inv)
        findings += self._quantity(inv)
        findings += self._unplanned_charges(inv)
        findings += self._tax_type(inv)
        findings += self._gstr2b(inv)
        findings += self._tds(inv, vendor)
        findings += self._msme(inv, vendor)
        return findings

    def _gstin(self, inv):
        ok, reason = gst.validate(inv["vendor_gstin"])
        if ok:
            return []
        return [Finding("GSTIN_INVALID", "Supplier GSTIN fails validation",
                        f"{inv['vendor_gstin']}: {reason}. ITC cannot be claimed on an invalid GSTIN.",
                        "critical", hard=True, amount_at_risk=sum(inv["taxes"].values()))]

    def _duplicate(self, inv):
        out = []
        base = _base_number(inv["invoice_number"])
        for other in self.book["invoices"]:
            if other["id"] == inv["id"] or other["vendor_id"] != inv["vendor_id"]:
                continue
            if other["received_date"] > inv["received_date"]:
                continue
            if other["invoice_number"].upper() == inv["invoice_number"].upper():
                out.append(Finding("DUPLICATE_EXACT", "Exact duplicate invoice number",
                                   f"{inv['invoice_number']} was already received on {other['received_date']}.",
                                   "critical", hard=True, amount_at_risk=inv["total"]))
            elif _base_number(other["invoice_number"]) == base:
                out.append(Finding("DUPLICATE_SUSPECTED", "Possible duplicate (same base invoice number)",
                                   f"{inv['invoice_number']} matches earlier {other['invoice_number']} "
                                   f"({_inr(other['total'])}, received {other['received_date']}).",
                                   "warning", amount_at_risk=inv["total"],
                                   facts={"earlier_invoice": other["invoice_number"], "earlier_total": other["total"]}))
        return out

    def _price(self, inv):
        po = self.pos.get(inv["po_number"])
        if not po:
            return [Finding("PO_MISSING", "No purchase order found", f"PO {inv['po_number']} not in system.", "critical")]
        po_rates = {l["sku"]: l["rate"] for l in po["lines"]}
        out, worst, over = [], 0.0, 0.0
        for line in inv["lines"]:
            po_rate = po_rates.get(line["sku"])
            if not po_rate:
                continue
            pct = (line["rate"] - po_rate) / po_rate * 100
            if pct > self.buyer["tolerance_pct"]:
                worst = max(worst, pct)
                over += (line["rate"] - po_rate) * line["qty"]
        if worst:
            out.append(Finding("PRICE_VARIANCE", f"Price {worst:.1f}% above PO",
                               f"Billed rates exceed PO {po['po_number']} by up to {worst:.2f}% "
                               f"(policy tolerance {self.buyer['tolerance_pct']}%). Excess: {_inr(over)} before GST.",
                               "warning", amount_at_risk=round(over, 2),
                               facts={"variance_pct": round(worst, 2), "excess_amount": round(over, 2)}))
        return out

    def _quantity(self, inv):
        grn = self.grns.get(inv["id"])
        if not grn:
            return [Finding("GRN_MISSING", "No goods receipt", "Nothing received against this invoice yet.", "critical")]
        received = {l["sku"]: l["qty_received"] for l in grn["lines"]}
        short = [(l, received.get(l["sku"], 0)) for l in inv["lines"] if l["qty"] > received.get(l["sku"], 0)]
        if not short:
            return []
        amt = sum((l["qty"] - r) * l["rate"] for l, r in short)
        detail = "; ".join(f"{l['sku']}: billed {l['qty']:g}, received {r:g}" for l, r in short)
        return [Finding("QTY_MISMATCH", "Billed quantity exceeds goods receipt",
                        f"{detail} (GRN {grn['grn_number']}). Over-billed: {_inr(amt)} before GST.",
                        "warning", amount_at_risk=round(amt, 2), facts={"overbilled_amount": round(amt, 2)})]

    def _unplanned_charges(self, inv):
        if not inv["extra_charges"]:
            return []
        base = sum(l["qty"] * l["rate"] for l in inv["lines"])
        out = []
        for c in inv["extra_charges"]:
            pct = c["amount"] / base * 100
            out.append(Finding("UNPLANNED_CHARGE", f"Charge not on PO: {c['desc']}",
                               f"{c['desc']} of {_inr(c['amount'])} = {pct:.1f}% of base value; no PO line covers it.",
                               "warning", amount_at_risk=c["amount"],
                               facts={"charge_pct": round(pct, 2), "charge_amount": c["amount"]}))
        return out

    def _tax_type(self, inv):
        intra = inv["vendor_gstin"][:2] == self.buyer["state_code"]
        t = inv["taxes"]
        if intra and t["igst"] > 0 or not intra and (t["cgst"] or t["sgst"]):
            want = "CGST+SGST" if intra else "IGST"
            return [Finding("TAX_TYPE_MISMATCH", "Wrong GST type for place of supply",
                            f"Supplier state {gst.state_of(inv['vendor_gstin'])} -> {want} expected.",
                            "critical", hard=True, amount_at_risk=sum(t.values()))]
        return []

    def _gstr2b(self, inv):
        if (inv["vendor_gstin"], inv["invoice_number"]) in self.gstr2b:
            return []
        tax = sum(inv["taxes"].values())
        return [Finding("GSTR2B_MISSING", "Not reflected in GSTR-2B",
                        f"Supplier has not reported {inv['invoice_number']} in GSTR-1, so it is absent from our GSTR-2B. "
                        f"Input tax credit of {_inr(tax)} is at risk if we pay in full.",
                        "warning", amount_at_risk=round(tax, 2), facts={"itc_at_risk": round(tax, 2)})]

    def _tds(self, inv, vendor):
        claimed, master = inv.get("tds_section_on_invoice"), vendor.get("tds_section")
        if not master:
            return [Finding("TDS_UNCLASSIFIED", "TDS section not set in vendor master",
                            f"Invoice states {claimed or 'no section'}; vendor master has none. "
                            "Wrong section breaks 26Q filing and the vendor's 26AS match.",
                            "warning", facts={"section_on_invoice": claimed})]
        if claimed and claimed != master:
            return [Finding("TDS_SECTION_CONFLICT", "TDS section differs from vendor master",
                            f"Invoice states {claimed}, vendor master says {master}.", "warning")]
        return []

    def _msme(self, inv, vendor):
        if not vendor.get("msme"):
            return []
        accepted = date.fromisoformat(inv["received_date"])
        due = accepted + timedelta(days=min(45, vendor["terms_days"]))
        return [Finding("MSME_45_DAY", f"MSME ({vendor['msme']['category']}) - pay by {due.isoformat()}",
                        f"{vendor['msme']['udyam']}. Section 43B(h): payment beyond 45 days of acceptance is "
                        f"disallowed as a deduction until paid, and MSMED Act interest applies. "
                        f"Vendor terms are {vendor['terms_days']} days; statutory limit wins.",
                        "info", facts={"pay_by": due.isoformat()})]


def summarise(findings: list[Finding]) -> dict:
    blocking = [f for f in findings if f.severity != "info"]
    return {
        "clean": not blocking,
        "hard_stop": any(f.hard for f in findings),
        "codes": [f.code for f in blocking],
    }
