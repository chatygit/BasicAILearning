# Demo runbook — Capital Markets Agent (11:00, 2026-08-21)

## Before you start (2 min)
- **The FIRST question of a session pays the load cost** (skill + business
  terms load once). Open with the throwaway warm-up below and TALK over it
  ("the agent is loading its domain knowledge — one-time per session").
  Everything after is faster.
- Say the product (ECM/DCM) when you know it — halves the work.
- One ask per message. Drill down using ids from the previous answer —
  that's the designed flow and it's fast.
- If a list says "more exist", ask "show the next 50" — paging demos well.

## Act 1 — quick wins (fast, single-object, no landmines)
1. **Warm-up:** "How many deals were priced in 2025, split by product?"
   (count metric, both products in one table — cheap and clean)
2. "List the 10 largest ECM deals of 2025 with issuer names"
   (issuer names are the NEW fix — call that out; also shows the
   date-desc + name + id ordering)
3. "Show DCM deals with 5 or more tranches" (pre-computed roll-ups —
   no hop, instant)
4. "List 5 recent convertible deals" (equity-type routing + sub-types
   shown alongside — the 'better response' the business asked for)
5. Pick a deal id from #2: "Who are the top 10 investors in deal <id> by
   allocation?" (drill-down via id = the designed handle; superlative
   shows top-3 tie handling)

## Act 2 — domain smarts (still quick, visibly clever)
6. "What's the biggest deal in EACH sector in 2025?" (top-N-per-group in
   ONE query — genuinely hard elsewhere, instant here)
7. "Top 10 investors in Healthcare deals over the last 2 years"
   (sector carried on orders — one request, no hops)
8. "Which orders on deal <id> were billed by Citi?" (billed-by is NEW —
   order-level billing attribution)
9. "Top 15 long-only investors in IPOs by allocation" (offering type on
   orders — one request; this used to be impossible)
10. "Show me demand vs allocation for deal <id> and how filled it was"
    (fill rate — CAO's use case family)

## Act 3 — the closers (heavier, run when warmed up)
11. "Look across all deals and give me Fidelity's indications and
    allocations; include the deal name and pricing date"
    (the CAO headline ask — shows entity disambiguation with a NUMBERED
    list; **reply with a number** to narrow: that moment is the most
    interactive beat of the demo)
12. Follow up: "only their ECM allocations above 1 million"
    (follow-up inherits scope — no re-specification)
13. "Give me insights on convertible issuance trends by quarter over the
    last 3 years" (time-grain bucketing + the summary/insight layer the
    CAO praised)

## Do NOT demo today (known, fixes shipping in next skill deploy)
- Multi-currency deal LISTINGS ("list multi-currency deals") — a table
  rendering bug (pipe splits a column) until the skill redeploy.
- "How much did <investor> invest in <instrument class>" (BlackRock
  shape) — cross-object recipe just rewritten; wait for the deploy.
- Region / settlement-date asks — they work but coverage is sparse, and
  the disclosure caveats read badly in a demo.
- Anything outside scope: market prices, ownership, fees, news, docs —
  the agent will (correctly) point to sibling agents; fine if asked, but
  don't seek it out.

## If something goes wrong
- Slow first answer: expected — narrate the one-time load.
- 0 rows: say "the agent tells us the real values instead of guessing" —
  the did-you-mean suggestion IS a feature; pick one and re-ask.
- A refusal or odd table: move on — "logged, that's what this testing
  round is for." Screenshot it to the ADK folder for me after.
- Timeout on a broad ask: re-ask scoped to one product or one year.
