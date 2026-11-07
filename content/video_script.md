# Demo video script (about 3 minutes)

Record at 1080p. Browser zoom 110%, terminal font large, notifications off.
Before recording: run `python scripts/replay_history.py`, then `uvicorn munshi.server:app --port 8000`.

## 0:00 – 0:30 · Intro (camera + app home)
> "Hi, I'm [NAME]. This is Munshi, an accounts payable agent for Indian finance teams that remembers how
> your people resolved every invoice exception, and uses it next time. Memory is powered by Hindsight."

**Screen:** app home with the November queue on the left. Point at the exception chips: price variance,
GSTR-2B missing, duplicate suspected.

## 0:30 – 1:00 · The problem (without memory)
> "Every AP team has one senior person who knows the vendor quirks. Without that knowledge, everything gets
> escalated."

**Screen:** open **Shree Balaji, SBP/2026-27/0588 (+2.2%)**. Click **Run Munshi**. Point at the
**left column, "Without memory"**: *Escalate to senior*, ₹0 paid.

## 1:00 – 2:30 · Live demo (memory on)
1. **Same invoice, right column, "With Hindsight memory"**: *Approve*. Click a purple memory-id chip; it
   scrolls to the recalled memory from 3 Sep: Meera's clause 7.2 rule, capped at 2.5%.
   > "Same model, same prompt. The only difference is the memory Hindsight recalled."
2. Open **SBP/2026-27/0601 (+4.1%)**, Run Munshi.
   > "It still escalates, to Meera by name, because it remembers her ceiling. Memory makes it precise, not
   > just permissive."
3. Open **Deccan Steel DST/1104/26**: pay the taxable ₹9.18 L, hold ₹1.65 L GST until GSTR-2B reflects.
4. Open **Coastal Freight CFC/BLR/2790**: open the **draft vendor email** citing Annexure B.
5. Open **Vrindavan Trading**: invalid GSTIN check digit, HARD CONTROL. HOLD regardless of memory.
6. Back on any invoice, type a note in the decision box, then **Record decision & teach Munshi**. Show
   the **Retained memory** panel with tags `vendor:… exception:… approver:…`.
   > "That note is now a dated memory in Hindsight. The next invoice from this vendor will recall it."
7. Click **Vendor brief (reflect)** on Coastal: Hindsight's reflect writes a briefing from the vendor's history.
8. **Learning curve** tab: share of exceptions resolved without a senior, August → November.

**Optional, 10 sec:** show `munshi/memory.py` with the `aretain` call and the two parallel `arecall` calls.

## 2:30 – 3:00 · Takeaway (camera)
> "What surprised me: the biggest gain wasn't prompting. It was scoping memory, by vendor and by exception
> type, and anchoring it to the invoice date. And the best moment is when the agent *refuses* to approve
> because it remembers the limit. Code is on GitHub. Thanks!"

## Title ideas
- My AP agent remembers what our controller decided in September
- I gave an invoice agent memory. Here's what it stopped escalating
- Same LLM, same prompt: why memory changed every invoice decision
- Building an accounts payable agent that knows when NOT to approve
- GST, GSTR-2B and agent memory: an AP agent built on Hindsight
