"""FastAPI app: serves the review UI and the agent API.

    uvicorn munshi.server:app --reload --port 8000
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, store
from .agent import Agent
from .memory import Memory
from .rules import Controls, summarise

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("munshi")

book = store.load_book()
memory = Memory()
agent = Agent(book, memory)
INV = {i["id"]: i for i in book["invoices"]}
VENDORS = {v["id"]: v for v in book["vendors"]}


@asynccontextmanager
async def lifespan(_app):
    if memory.enabled:
        try:
            await memory.ensure_bank()
        except Exception as e:
            log.error("Hindsight bank setup failed: %s", e)
    yield


app = FastAPI(title="Munshi", lifespan=lifespan)
WEB = config.ROOT / "web"


def _invoice(inv_id: str) -> dict:
    if inv_id not in INV:
        raise HTTPException(404, f"unknown invoice {inv_id}")
    return INV[inv_id]


@app.get("/api/health")
async def health():
    return {
        "hindsight_url": config.HINDSIGHT_URL,
        "hindsight_configured": memory.enabled,
        "bank_id": memory.bank,
        "llm_configured": bool(config.LLM_API_KEY),
        "llm_model": config.LLM_MODEL,
    }


@app.get("/api/book")
async def get_book():
    state = store.load_state()
    controls = Controls(book)
    rows = []
    for inv in sorted(book["invoices"], key=lambda i: (i["received_date"], i["id"])):
        s = summarise(controls.run(inv))
        rows.append({
            "id": inv["id"], "phase": inv["phase"], "invoice_number": inv["invoice_number"],
            "vendor": VENDORS[inv["vendor_id"]]["name"], "vendor_id": inv["vendor_id"],
            "received_date": inv["received_date"], "total": inv["total"], "codes": s["codes"],
            "hard_stop": s["hard_stop"],
            "decision": state["decisions"].get(inv["id"]),
            "analysed": "on" in state["analyses"].get(inv["id"], {}),
        })
    return {"buyer": book["buyer"], "vendors": book["vendors"], "invoices": rows}


@app.get("/api/invoices/{inv_id}")
async def get_invoice(inv_id: str):
    inv = _invoice(inv_id)
    po = next((p for p in book["purchase_orders"] if p["po_number"] == inv["po_number"]), None)
    grn = next((g for g in book["grns"] if g["invoice_id"] == inv_id), None)
    state = store.load_state()
    return {"invoice": inv, "vendor": VENDORS[inv["vendor_id"]], "po": po, "grn": grn,
            "findings": [f.to_dict() for f in agent.controls.run(inv)],
            "analyses": state["analyses"].get(inv_id, {}), "decision": state["decisions"].get(inv_id)}


class AnalyseReq(BaseModel):
    compare: bool = True


@app.post("/api/invoices/{inv_id}/analyse")
async def analyse(inv_id: str, req: AnalyseReq):
    inv = _invoice(inv_id)
    if req.compare:
        on, off = await asyncio.gather(agent.analyse(inv, True), agent.analyse(inv, False))
        result = {"on": on, "off": off}
    else:
        result = {"on": await agent.analyse(inv, True)}
    state = store.load_state()
    state["analyses"][inv_id] = result
    store.save_state(state)
    return result


class DecisionReq(BaseModel):
    decision: str  # APPROVED | PARTIAL | REJECTED | HELD | ROUTED
    by: str
    role: str
    note: str
    accepted_agent: bool = False


@app.post("/api/invoices/{inv_id}/decide")
async def decide(inv_id: str, req: DecisionReq):
    inv = _invoice(inv_id)
    if not req.note.strip():
        raise HTTPException(400, "A note is required: it is what Munshi learns from.")
    state = store.load_state()
    analysis = state["analyses"].get(inv_id, {}).get("on")
    findings = [f for f in (analysis["findings"] if analysis else []) if f["severity"] != "info"]
    codes = [f["code"] for f in findings]
    decision = {**req.model_dump(), "date": inv["received_date"], "findings": findings}
    retained = None
    if memory.enabled:
        try:
            retained = await memory.retain_decision(inv, VENDORS[inv["vendor_id"]], codes, decision,
                                                    analysis["decision"] if analysis else None)
        except Exception as e:
            log.exception("retain failed")
            raise HTTPException(502, f"Hindsight retain failed: {e}")
    decision.pop("findings")
    state["decisions"][inv_id] = decision
    store.save_state(state)
    return {"decision": decision, "retained": retained}


@app.get("/api/vendors/{vendor_id}/brief")
async def vendor_brief(vendor_id: str):
    if vendor_id not in VENDORS:
        raise HTTPException(404, "unknown vendor")
    try:
        return await memory.vendor_brief(VENDORS[vendor_id])
    except Exception as e:
        raise HTTPException(502, f"Hindsight reflect failed: {e}")


@app.get("/api/memory")
async def explore(q: str, vendor_id: str | None = None):
    try:
        return {"results": await memory.explore(q, vendor_id)}
    except Exception as e:
        raise HTTPException(502, f"Hindsight recall failed: {e}")


@app.get("/api/metrics")
async def get_metrics():
    return store.metrics(book, store.load_state())


@app.get("/")
async def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
