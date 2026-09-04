# Token-economy review (2026-09-04)

Trigger: complaints = slowness + token burn; observed 181,094 prompt tokens on a
single Gemini invocation (chat-debug trace, 2026-09-02). Config keeps growing
with every fix round — this review measures where tokens live and plans the cut.

## Measurements (today, real payloads — catalogs rendered via OntologyRegistry)

**Static tax (in EVERY turn's context after load_skill):**
| Artifact | Size | ~Tokens |
|---|---|---|
| SKILL.md | 87,050 chars | ~22,000 |
| agents.yaml routing instructions | 20,618 chars | ~5,000 |

**Per-question dynamic tax (one catalog fetch, then PERMANENT in the convo):**
| Catalog | ~Tokens |
|---|---|
| tranche | 16,200 |
| order | 12,200 |
| deal | 11,800 |
| entity | 5,200 |
| hedge / trade / hedge_trade / designation / trade_syndicate | 1,300–3,400 each |
| all nine (never fetched together — routing-index design prevents) | ~58,000 |

**Accumulators (the rest of the 181k):** conversation history carrying every tool
response — and every run_bqs_query response echoes the FULL generated SQL as
`sql_audit` (a USD-style query with in-lists = thousands of tokens, per response),
plus suggestion/disambiguation blocks. This is the V1 `validation_rules`
token-hog lesson recurring in a new spot.

A 3-object conversation: ~27k static + ~40k catalogs + history ⇒ the observed
181k is fully explained. Token bloat IS slowness twice over: model latency per
turn scales with prompt size, and it compounds with the query latency work.

## The structural mistake to stop repeating

Every fix round added prose to SKILL (pay-EVERY-turn) even when the rule was
object-specific (pay-only-when-fetched if it lived in that object's yaml).
Doctrine placement rule from now on: **cross-object rules → SKILL; object rules →
that object's yaml how_to_use; descriptions telegraphic.** A fix's token delta is
part of its review.

## Plan

**Phase 1 — config-only compression (no approvals; the next config iteration
AFTER the pending push ships):**
1. Catalog compression: tranche 16.2k → ≤8k tokens; order/deal ~12k → ≤7k each.
   Telegraphic descriptions; kill per-filter boilerplate repetition ("TEXT ids —
   quote, max 40 per in-list" once in how_to_use, not per filter); keep
   vocabulary/value lists intact (they are load-bearing). Target: one-question
   convo drops ~15-20k tokens.
2. SKILL layering: 87k chars → ≤45k (~11k tokens). MOVE object-specific doctrine
   into the owning yaml (identifier/casing → tranche; hedge routing detail →
   hedge; designation/closeout → designation; currency vocab → deal). SKILL
   keeps: routing, iron rules, hard budget, presentation, traps, cross-object
   doctrine. Gate pins move with the text (path updates — mechanical, the pins
   exist to survive exactly this).
3. agents.yaml routing bullets trim (~5k → ~2k tokens).
Net static+first-catalog: ~50k → ~25k tokens.

**Phase 2 — server (release train, with cache/timeout/unmasking):**
1. `sql_audit` flag: ECM_DCM_SQL_AUDIT=summary|full|off, default SUMMARY
   (truncated) — full SQL already lives in server logs. Biggest response-side
   win; per-response savings recur across the whole conversation history.
2. Cap suggestion/disambiguation block sizes; trim repeated hint texts.

**Phase 3 — platform (agent team):**
1. Gemini context caching for the static prefix (SKILL + instructions):
   ~27k static tokens become cached-prefix — latency + cost drop without
   deleting a word. Ask the ADK/platform team whether cached content is
   available on the Vertex path.
2. Token telemetry: ADK already surfaces usageMetadata per invocation — log
   promptTokenCount per turn as a metric, alarm on a budget (e.g. 100k).

## Sequencing (recommendation)
Ship the pending config push AS-IS first — it unlocks the hedge domain and every
queued fix; delaying it on a rewrite costs more than the tokens do. Phase 1 is
the immediately-following config iteration (config iterates freely). Phase 2
rides the already-planned release train. The "rewrites ON HOLD" freeze from the
redundancy review is hereby superseded by this plan — the token angle is the
justification that review lacked.

## Status
- [x] measured (this doc)
- [ ] config push ships (prerequisite)
- [ ] Phase 1 compression (target numbers above; gate pins updated in lockstep)
- [ ] Phase 2 server items registered on the train
- [ ] Phase 3 platform asks (context caching; token telemetry)
