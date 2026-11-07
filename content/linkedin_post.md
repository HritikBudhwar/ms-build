An AP agent that approves more invoices is easy.
One that knows when *not* to is the hard part.

I built Munshi, an accounts payable agent for Indian finance teams, on Hindsight agent memory.

What changed once it could remember:

- Before: a 2.2% price variance gets escalated. After: it's approved under the clause 7.2 tolerance procurement set in September.
- At 4.1%, it still escalates, now to the exact person who set the 2.5% cap.
- Vendor missing from GSTR-2B: pay the taxable value, hold the GST. The controller's standing rule.
- Invalid GSTIN: HOLD. Memory never overrides a hard control.

Tricks worth copying: tag memories by vendor AND by exception type, and anchor recall to the invoice date.

Code: [GitHub link]

#AIAgents #AgentMemory #Hindsight #LLM
