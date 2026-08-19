# Latency tests — 5 runs, in this order

The single largest item in every trace is the final synthesis LLM call
(29–48s). Nothing in the repo can tell me **why**. These five runs settle it,
plus the two other open questions. T1+T4 alone are worth more than the rest.

For each run capture: the **full trace** (all `call_llm` durations) and the
**full MCP log** for that invocation.

---

## T1 — one-row answer  ⭐ HIGHEST VALUE

> **"How many DCM deals priced in 2024?"**

Returns a single scalar. Almost nothing enters the model's context, and the
answer should be one sentence.

| If the final `call_llm` is | Then synthesis is | And the lever is |
|---|---|---|
| still ~25–45s | **output/thinking-bound** | shorten the answer contract, cap thinking budget, split formatting from insight |
| drops to ~5–10s | **input-bound** | cap rows into context, trim the response payload |

This one measurement decides half the plan. Everything else is secondary.

---

## T2 — the same question twice, same session

Run **T1 again, verbatim, without starting a new session.**

Isolates cold vs warm cost:

- If turn 2's first `call_llm` drops a lot → a prefix cache is already working,
  and the caching lever is partly spent.
- If `discover_business_terms` is skipped → per-session catalog caching works.
  (One MCP log already showed 0.0038s, so something is caching — this confirms
  whether it survives across turns.)
- If turn 2 costs the same as turn 1 → **nothing is being reused**, and the
  cached-prefix work is worth its full estimate.

---

## T3 — the 2-hop case, full log

> **"List multi currency deals"**  (the debug-6 ask)

I need **both** `run_bqs_query` SQL statements from the MCP log, not the trace.
The question is why the second request was needed — whether it is the
one-metric-per-request limit, the lack of OR, or the agent re-asking. That
determines whether the fix is planner, ontology, or prompt.

---

## T4 — large result, for contrast with T1

> **"List the orders for the largest DCM deal in 2024"**  (or any ask that
> returns the full 50 rows)

Same discriminator as T1 from the other end. T1 vs T4 gives two points on the
input-size axis:

- both slow → output/thinking-bound, result size is irrelevant
- T4 much slower than T1 → input-bound, and row-capping pays

---

## T5 — token counts (may be free)

Does the trace UI expose per-call token counts — **input**, **output**,
**thinking**, and **cached**? Gemini 2.5 Pro reports thinking tokens
separately, and any context caching shows as a cached-token count.

If those numbers exist, they answer T1/T4 directly and far more precisely than
wall-clock. **If they are not exposed anywhere, say so — that is itself a
finding**, because it means nobody can attribute model cost today.

---

## Two questions that need no run

1. **debug-10** appeared to show SKILL.md text (*"The contract (one loop,
   fewest hops)…"*) in what looked like the chat pane. Was that the chat, or
   the trace inspector showing the prompt? If it is the chat, the agent is
   echoing internal doctrine to users — a presentation bug and a
   confidentiality one.
2. Have the four old `ecm_dcm_*.yaml` files been deleted from the MCP repo?
   The startup log showed them loading and being disabled. Harmless now, but
   if `BQS_ENABLED_SOURCES` is ever set to `*`, eight sources load.
