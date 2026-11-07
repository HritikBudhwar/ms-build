"""Replay Aug-Oct 2026 through Munshi: the agent analyses each historical invoice with
whatever memory it has *at that point*, then the real human decision is retained.

This is how the bank gets its memory - the same path a live reviewer uses, not a bulk import.

    python scripts/replay_history.py           # fresh bank, full replay
    python scripts/replay_history.py --keep    # keep existing bank
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from munshi import store  # noqa: E402
from munshi.agent import Agent  # noqa: E402
from munshi.memory import Memory  # noqa: E402

SAME_OUTCOME = {"APPROVE": "APPROVED", "APPROVE_PARTIAL": "PARTIAL", "REQUEST_VENDOR_CORRECTION": "REJECTED"}


async def main(keep: bool):
    book = store.load_book()
    memory = Memory()
    if not memory.enabled:
        sys.exit("Set HINDSIGHT_API_KEY in .env first.")
    await memory.ensure_bank(reset=not keep)
    store.reset_state()
    agent = Agent(book, memory)
    vendors = {v["id"]: v for v in book["vendors"]}
    state = store.load_state()

    history = sorted((i for i in book["invoices"] if i["phase"] == "history"), key=lambda i: (i["received_date"], i["id"]))
    for inv in history:
        human = book["history_decisions"][inv["id"]]
        analysis = await agent.analyse(inv, use_memory=True)
        d = analysis["decision"]
        findings = [f for f in analysis["findings"] if f["severity"] != "info"]
        decision = {**human, "date": inv["received_date"], "findings": findings,
                    "accepted_agent": SAME_OUTCOME.get(d["action"]) == human["decision"]}
        await memory.retain_decision(inv, vendors[inv["vendor_id"]], [f["code"] for f in findings], decision, d)
        decision.pop("findings")
        state["analyses"][inv["id"]] = {"on": analysis}
        state["decisions"][inv["id"]] = decision
        store.save_state(state)
        print(f"{inv['received_date']}  {inv['id']:<10} {vendors[inv['vendor_id']]['name'][:28]:<28} "
              f"agent={d['action']:<26} human={human['decision']:<9} memories={len(analysis['memories'])}")
    await memory.client.aclose()
    print("\nHistory replayed. Start the app and open the November queue.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    asyncio.run(main(ap.parse_args().keep))
