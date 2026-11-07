"""Local JSON state: agent analyses and human decisions. Memory itself lives in Hindsight."""

import json
import threading

from . import config

_lock = threading.Lock()


def load_book() -> dict:
    return json.loads(config.BOOK_PATH.read_text())


def _empty():
    return {"analyses": {}, "decisions": {}}


def load_state() -> dict:
    if not config.STATE_PATH.exists():
        return _empty()
    try:
        return json.loads(config.STATE_PATH.read_text())
    except json.JSONDecodeError:
        return _empty()


def save_state(state: dict):
    with _lock:
        tmp = config.STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False))
        tmp.replace(config.STATE_PATH)


def reset_state():
    save_state(_empty())


def metrics(book: dict, state: dict) -> dict:
    """Learning curve: for each decided invoice in date order, did it need a senior person?"""
    inv_by_id = {i["id"]: i for i in book["invoices"]}
    points = []
    for inv_id, d in sorted(state["decisions"].items(), key=lambda kv: (inv_by_id[kv[0]]["received_date"], kv[0])):
        a = state["analyses"].get(inv_id, {}).get("on")
        if not a:
            continue
        exceptions = bool(a["summary"]["codes"])
        points.append({
            "invoice_id": inv_id,
            "date": inv_by_id[inv_id]["received_date"],
            "phase": inv_by_id[inv_id]["phase"],
            "had_exception": exceptions,
            "needs_senior": a["needs_senior"],
            "memories_used": sum(1 for r in a["decision"].get("reasoning", []) if r.get("memory_ids")),
            "accepted": d.get("accepted_agent", False),
        })
    exc = [p for p in points if p["had_exception"]]

    def rate(ps):
        return round(100 * sum(1 for p in ps if not p["needs_senior"]) / len(ps)) if ps else None

    return {
        "points": points,
        "history_resolved_without_senior_pct": rate([p for p in exc if p["phase"] == "history"]),
        "live_resolved_without_senior_pct": rate([p for p in exc if p["phase"] == "live"]),
        "exceptions_total": len(exc),
        "accepted_pct": round(100 * sum(p["accepted"] for p in points) / len(points)) if points else None,
    }
