"""Generate the synthetic AP book for Kaveri Precision Components Pvt Ltd.

Run once; the output in data/ is committed so the demo is deterministic.
    python scripts/generate_data.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from munshi.gstin import with_checksum  # noqa: E402

DATA = ROOT / "data"

BUYER = {
    "name": "Kaveri Precision Components Pvt Ltd",
    "gstin": with_checksum("29AAHCK4821M1Z"),
    "address": "Plot 41, Bommasandra Industrial Area, Bengaluru 560099",
    "state_code": "29",
    "tolerance_pct": 1.0,
}

VENDORS = [
    {
        "id": "V001", "name": "Shree Balaji Packaging Pvt Ltd", "city": "Peenya, Bengaluru",
        "gstin": with_checksum("29AAJCS7712K1Z"), "msme": {"udyam": "UDYAM-KR-03-0041187", "category": "Micro"},
        "terms_days": 30, "category": "Packaging", "tds_section": "194Q", "email": "accounts@balajipack.in",
    },
    {
        "id": "V002", "name": "Coastal Freight Carriers", "city": "Ambattur, Chennai",
        "gstin": with_checksum("33AAFFC3390P1Z"), "msme": None,
        "terms_days": 30, "category": "Logistics (GTA)", "tds_section": "194C", "email": "billing@coastalfreight.co.in",
    },
    {
        "id": "V003", "name": "Deccan Steel Traders", "city": "Balanagar, Hyderabad",
        "gstin": with_checksum("36AAKFD5521H1Z"), "msme": None,
        "terms_days": 45, "category": "Raw material", "tds_section": "194Q", "email": "accounts@deccansteel.in",
    },
    {
        "id": "V004", "name": "Nimbus Cloudworks Pvt Ltd", "city": "Hinjawadi, Pune",
        "gstin": with_checksum("27AADCN9087Q1Z"), "msme": None,
        "terms_days": 30, "category": "IT services", "tds_section": None, "email": "ar@nimbuscloudworks.com",
    },
    {
        "id": "V005", "name": "Sri Lakshmi Electricals", "city": "Hebbal Industrial Area, Mysuru",
        "gstin": with_checksum("29ABMPL6230D1Z"), "msme": {"udyam": "UDYAM-KR-27-0009823", "category": "Small"},
        "terms_days": 60, "category": "Electricals", "tds_section": "194Q", "email": "srilakshmi.elec@gmail.com",
    },
    {
        "id": "V006", "name": "Apex Industrial Supplies", "city": "Bhosari MIDC, Pune",
        "gstin": with_checksum("27AAQFA2245L1Z"), "msme": None,
        "terms_days": 45, "category": "Tooling", "tds_section": "194Q", "email": "invoices@apexindustrial.in",
    },
    {
        # New vendor onboarded by a plant user; the check digit on the invoice is wrong.
        "id": "V007", "name": "Vrindavan Trading Co", "city": "Naraina, New Delhi",
        "gstin": "07AAIFV1189B1Z" + ("A" if with_checksum("07AAIFV1189B1Z")[-1] != "A" else "B"),
        "msme": None, "terms_days": 30, "category": "Consumables", "tds_section": "194Q", "email": "vrindavantrading@yahoo.co.in",
    },
]

# sku -> (description, hsn/sac, gst_rate)
ITEMS = {
    "PK-CB-5PLY": ("5-ply corrugated box 600x400x400", "4819", 18),
    "PK-SEP-01": ("Corrugated separator sheet", "4819", 18),
    "LG-FTL-BLR-CHN": ("FTL freight Bengaluru-Chennai, 32ft MXL", "996511", 12),
    "RM-HR-2MM": ("HR sheet IS 2062 E250, 2mm", "7208", 18),
    "RM-CR-1.2": ("CR coil IS 513, 1.2mm", "7209", 18),
    "IT-ERP-IMPL": ("ERP implementation & managed services (monthly)", "998314", 18),
    "EL-CBL-4C16": ("4C x 16 sq.mm armoured Cu cable (m)", "8544", 18),
    "EL-MCB-63A": ("63A TP MCB", "8536", 18),
    "TL-CARB-10": ("Solid carbide end mill 10mm", "8207", 18),
    "TL-INS-CNMG": ("CNMG 120408 turning insert (box of 10)", "8207", 18),
    "CS-GLV-NIT": ("Nitrile gloves (box of 100)", "4015", 12),
}

# Each scenario: invoice id, phase, vendor, invoice no., dates, PO lines (sku, qty, po_rate),
# invoice overrides, GRN overrides, extra charges, in GSTR-2B?
SCENARIOS = [
    # ---- history: Aug-Oct 2026, decided by people before Munshi had any memory ----
    dict(id="INV-0901", phase="history", v="V006", no="AIS/26-27/0388", inv="2026-08-11", rcv="2026-08-13",
         po="4500011870", lines=[("TL-CARB-10", 40, 2450.00), ("TL-INS-CNMG", 25, 3890.00)]),
    dict(id="INV-0902", phase="history", v="V001", no="SBP/2026-27/0412", inv="2026-09-01", rcv="2026-09-03",
         po="4500012231", lines=[("PK-CB-5PLY", 2200, 86.50), ("PK-SEP-01", 4000, 9.20)],
         rate_pct={"PK-CB-5PLY": 2.0, "PK-SEP-01": 2.0}),
    dict(id="INV-0903", phase="history", v="V002", no="CFC/BLR/2611", inv="2026-09-08", rcv="2026-09-10",
         po="4500012304", lines=[("LG-FTL-BLR-CHN", 6, 38500.00)], surcharge_pct=6.5),
    dict(id="INV-0904", phase="history", v="V003", no="DST/0917/26", inv="2026-09-15", rcv="2026-09-18",
         po="4500012342", lines=[("RM-HR-2MM", 12.5, 61200.00), ("RM-CR-1.2", 6.0, 68900.00)], in_2b=False),
    dict(id="INV-0905A", phase="history", v="V005", no="SLE/1187", inv="2026-09-19", rcv="2026-09-20",
         po="4500012371", lines=[("EL-CBL-4C16", 450, 412.00), ("EL-MCB-63A", 18, 1860.00)],
         rate_pct={"EL-CBL-4C16": 3.4}),
    dict(id="INV-0905", phase="history", v="V005", no="SLE/1187-R", inv="2026-09-23", rcv="2026-09-24",
         po="4500012371", lines=[("EL-CBL-4C16", 450, 412.00), ("EL-MCB-63A", 18, 1860.00)]),
    dict(id="INV-0906", phase="history", v="V002", no="CFC/BLR/2688", inv="2026-10-03", rcv="2026-10-06",
         po="4500012455", lines=[("LG-FTL-BLR-CHN", 8, 38500.00)], surcharge_pct=11.2),
    dict(id="INV-0907", phase="history", v="V004", no="NCW/INV/26/1044", inv="2026-10-01", rcv="2026-10-12",
         po="4500012390", lines=[("IT-ERP-IMPL", 1, 385000.00)], tds_claimed="194C"),
    dict(id="INV-0908", phase="history", v="V001", no="SBP/2026-27/0507", inv="2026-10-13", rcv="2026-10-15",
         po="4500012480", lines=[("PK-CB-5PLY", 1800, 86.50)], rate_pct={"PK-CB-5PLY": 1.8}),
    dict(id="INV-0909", phase="history", v="V006", no="AIS/26-27/0461", inv="2026-10-20", rcv="2026-10-22",
         po="4500012511", lines=[("TL-INS-CNMG", 120, 3890.00)], grn_qty={"TL-INS-CNMG": 100}),
    # ---- live queue: first week of November 2026 ----
    dict(id="INV-1101", phase="live", v="V006", no="AIS/26-27/0502", inv="2026-11-02", rcv="2026-11-03",
         po="4500012602", lines=[("TL-CARB-10", 60, 2450.00)]),
    dict(id="INV-1102", phase="live", v="V001", no="SBP/2026-27/0588", inv="2026-11-02", rcv="2026-11-03",
         po="4500012617", lines=[("PK-CB-5PLY", 2600, 86.50), ("PK-SEP-01", 5000, 9.20)],
         rate_pct={"PK-CB-5PLY": 2.2, "PK-SEP-01": 2.2}),
    dict(id="INV-1103", phase="live", v="V002", no="CFC/BLR/2790", inv="2026-11-03", rcv="2026-11-04",
         po="4500012625", lines=[("LG-FTL-BLR-CHN", 7, 38500.00)], surcharge_pct=9.6),
    dict(id="INV-1104", phase="live", v="V003", no="DST/1104/26", inv="2026-11-02", rcv="2026-11-04",
         po="4500012630", lines=[("RM-HR-2MM", 15.0, 61200.00)], in_2b=False),
    dict(id="INV-1105A", phase="history", v="V005", no="SLE/1342", inv="2026-10-29", rcv="2026-10-30",
         po="4500012560", lines=[("EL-CBL-4C16", 600, 412.00)], grn_qty={"EL-CBL-4C16": 560}),
    dict(id="INV-1105", phase="live", v="V005", no="SLE/1342-R", inv="2026-11-04", rcv="2026-11-05",
         po="4500012560", lines=[("EL-CBL-4C16", 560, 412.00)]),
    dict(id="INV-1106", phase="live", v="V007", no="VTC/2026/118", inv="2026-11-04", rcv="2026-11-05",
         po="4500012641", lines=[("CS-GLV-NIT", 300, 640.00)], in_2b=False),
    dict(id="INV-1107", phase="live", v="V004", no="NCW/INV/26/1187", inv="2026-11-01", rcv="2026-11-06",
         po="4500012390", lines=[("IT-ERP-IMPL", 1, 385000.00)], tds_claimed="194C"),
    dict(id="INV-1108", phase="live", v="V001", no="SBP/2026-27/0601", inv="2026-11-05", rcv="2026-11-06",
         po="4500012655", lines=[("PK-CB-5PLY", 3000, 86.50)], rate_pct={"PK-CB-5PLY": 4.1}),
    dict(id="INV-1109", phase="live", v="V006", no="AIS/26-27/0519", inv="2026-11-05", rcv="2026-11-07",
         po="4500012660", lines=[("TL-INS-CNMG", 80, 3890.00)], grn_qty={"TL-INS-CNMG": 64}),
]

# What the humans actually decided on the history invoices. These are replayed into
# Hindsight by scripts/replay_history.py, in date order, through the same agent path.
HISTORY_DECISIONS = {
    "INV-0901": dict(by="Ravi Kumar", role="AP Executive", decision="APPROVED",
                     note="Clean three-way match. Paid on terms."),
    "INV-0902": dict(by="Meera Iyer", role="Head of Procurement", decision="APPROVED",
                     note="Rate contract RC-SBP-2025 clause 7.2 gives Shree Balaji an annual escalation linked to the "
                          "kraft paper index, capped at 2.5%, effective 1 April. Our PO master was never updated. "
                          "Accept SBP price variance up to 2.5% without escalating to me. Anything above 2.5% comes to me."),
    "INV-0903": dict(by="Arjun Rao", role="Logistics Manager", decision="APPROVED",
                     note="Diesel-linked fuel surcharge is allowed under transport agreement TA-CFC-24, Annexure B, "
                          "up to 8% of base freight. It is never on the PO. Up to 8% is fine; above 8% push back."),
    "INV-0904": dict(by="Kavya Menon", role="Financial Controller", decision="PARTIAL",
                     note="Deccan Steel files GSTR-1 late - usually between the 20th and 25th, not by the 11th - so their "
                          "invoices miss our first GSTR-2B. Do not block a key steel supplier: release the taxable value, "
                          "hold only the GST component until the invoice shows in 2B. It reflected in the next cycle."),
    "INV-0905A": dict(by="Ravi Kumar", role="AP Executive", decision="REJECTED",
                      note="Cable rate billed 3.4% above PO. Sent back to Sri Lakshmi Electricals for correction."),
    "INV-0905": dict(by="Ravi Kumar", role="AP Executive", decision="APPROVED",
                     note="Sri Lakshmi Electricals re-sends corrected invoices with a '-R' suffix. SLE/1187-R replaces "
                          "SLE/1187, which they cancelled with credit note CN/SLE/044. Not a duplicate - pay the -R "
                          "version and make sure the original is never paid. MSME (Small): keep within 45 days."),
    "INV-0906": dict(by="Arjun Rao", role="Logistics Manager", decision="REJECTED",
                     note="Fuel surcharge of 11.2% is over the 8% Annexure B cap. I emailed Coastal citing Annexure B and "
                          "they re-issued at 7.5% within two days. Pushback works with Coastal - always cite Annexure B."),
    "INV-0907": dict(by="Kavya Menon", role="Financial Controller", decision="APPROVED",
                     note="Nimbus Cloudworks marks 194C on its invoices, but our tax consultant (opinion dated 9 Oct 2026) "
                          "classified their ERP implementation and managed services as fees for technical services: "
                          "deduct TDS under 194J(b) at 2%, not 194C. The rate is the same but the section matters for "
                          "26Q filing and their 26AS match. Update vendor master to 194J(b)."),
    "INV-0908": dict(by="Ravi Kumar", role="AP Executive", decision="APPROVED",
                     note="1.8% variance, within Meera's 2.5% SBP escalation tolerance. Approved without escalation."),
    "INV-0909": dict(by="Ravi Kumar", role="AP Executive", decision="PARTIAL",
                     note="Apex short-shipped 20 inserts but billed 120. They always ship the balance in the next "
                          "consignment and bill it then if we ask. Pay only for the GRN quantity and ask Apex for a credit "
                          "note on the difference - no need to reject the whole invoice."),
    "INV-1105A": dict(by="Ravi Kumar", role="AP Executive", decision="REJECTED",
                      note="Billed 600 m, GRN shows 560 m. Returned to Sri Lakshmi Electricals for a revised invoice."),
}


def build():
    vendors = {v["id"]: v for v in VENDORS}
    pos, grns, invoices, gstr2b = [], [], [], []
    for s in SCENARIOS:
        v = vendors[s["v"]]
        po_lines, grn_lines, inv_lines = [], [], []
        for sku, qty, rate in s["lines"]:
            desc, hsn, gst = ITEMS[sku]
            po_lines.append(dict(sku=sku, desc=desc, hsn=hsn, qty=qty, rate=rate, gst_rate=gst))
            grn_lines.append(dict(sku=sku, qty_received=s.get("grn_qty", {}).get(sku, qty)))
            bump = s.get("rate_pct", {}).get(sku, 0.0)
            inv_lines.append(dict(sku=sku, desc=desc, hsn=hsn, qty=qty, rate=round(rate * (1 + bump / 100), 2), gst_rate=gst))
        if not any(p["po_number"] == s["po"] for p in pos):
            pos.append(dict(po_number=s["po"], vendor_id=v["id"], date=s["inv"], lines=po_lines))
        grns.append(dict(grn_number="GRN-" + s["id"][4:], po_number=s["po"], invoice_id=s["id"], date=s["rcv"], lines=grn_lines))

        taxable = sum(l["qty"] * l["rate"] for l in inv_lines)
        charges = []
        if "surcharge_pct" in s:
            amt = round(taxable * s["surcharge_pct"] / 100, 2)
            charges.append(dict(desc="Fuel surcharge (diesel-linked)", amount=amt, gst_rate=12))
        taxable += sum(c["amount"] for c in charges)
        tax = sum(l["qty"] * l["rate"] * l["gst_rate"] / 100 for l in inv_lines) + sum(c["amount"] * c["gst_rate"] / 100 for c in charges)
        intra = v["gstin"][:2] == BUYER["state_code"]
        taxes = dict(cgst=round(tax / 2, 2), sgst=round(tax / 2, 2), igst=0.0) if intra else dict(cgst=0.0, sgst=0.0, igst=round(tax, 2))
        inv = dict(
            id=s["id"], phase=s["phase"], invoice_number=s["no"], vendor_id=v["id"], vendor_gstin=v["gstin"],
            invoice_date=s["inv"], received_date=s["rcv"], po_number=s["po"], place_of_supply="29-Karnataka",
            lines=inv_lines, extra_charges=charges, taxable_value=round(taxable, 2), taxes=taxes,
            total=round(taxable + tax, 2), tds_section_on_invoice=s.get("tds_claimed"),
        )
        invoices.append(inv)
        if s.get("in_2b", True):
            gstr2b.append(dict(supplier_gstin=v["gstin"], invoice_number=s["no"], invoice_date=s["inv"],
                               taxable_value=inv["taxable_value"], tax=round(tax, 2)))

    out = dict(buyer=BUYER, vendors=VENDORS, purchase_orders=pos, grns=grns, invoices=invoices,
               gstr2b=gstr2b, history_decisions=HISTORY_DECISIONS)
    DATA.mkdir(exist_ok=True)
    (DATA / "ap_book.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {len(invoices)} invoices, {len(VENDORS)} vendors -> data/ap_book.json")


if __name__ == "__main__":
    build()
