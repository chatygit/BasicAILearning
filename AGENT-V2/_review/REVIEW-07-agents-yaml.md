# Review 07 — `adk/config/agents.yaml` (`capital_markets_agent_v2`)

## Verdict

**The survival kit is there, and it is good.** The v1 lesson — skill loading is
discretionary, so the rules that must never fail have to live in the agent
instruction — was clearly learned. The nine-point CORE CONTRACT restates grain
routing, product scoping, the units doctrine, metric routing, B&D, HAVING/Top-N,
date windows and rejection handling *without* the skill. `"Loading a skill does
NOT end your turn"` is in there, which is the exact turn-ending bug from v1.

Seven findings. Two are contradictions between this file and the skill, and one
answers a question I had listed as blocking.

---

## G1. It answers the discovery question — but only about the CALL, not the tool

> `1. ALWAYS call `discover_business_terms` FIRST (no arguments) and read the
> returned FOUR objects…`

> **CORRECTED after reading `mcpserver.py` (REVIEW-08 H1):** I concluded from
> this line that discovery *cannot* be scoped. Wrong — the tool signature is
> `discover_business_terms(source: str | None = None)`. This instruction is what
> makes it fetch all four catalogs; the tool has always accepted one name. The
> fix is config-only and is now applied to rule 1. Everything below about the
> token cost still holds — it was simply self-inflicted rather than imposed.

So the token stack on **every** turn is: agent instruction (~1.5k) + four
catalogs with their `how_to_use`/`usage_notes`/`examples` (the four ontology
files total ~2,000 lines) + tool descriptions + the skill once loaded (~5k) +
conversation history. Against v1's single ~7k schema.

Two consequences, and the second is the one that bites:
- **Cost**, which is merely money.
- **Reliability.** v1 produced an empty `finishReason: STOP` at 91,676 prompt
  tokens. If v2 sits higher than that from turn one, "the response just abruptly
  stops" comes back — and this file runs `gemini-2.5-pro`, so each of those
  turns is also slow.

Fix stands as written: two-stage discovery — a thin index (four names + grain +
one routing line, ~200 tokens) then the full catalog for the chosen object only.
**Measure `promptTokenCount` on one v2 turn before doing anything else.**

I added *"Discovery is per-SESSION knowledge: once you have it, do not call it
again in the same conversation"* to point 1. If discovery currently fires per
turn, that line alone is a large win for free.

## G2. The instruction told the agent to leak the ontology — while the skill forbids it

Original, last line before `tools:`:

> `Present results with a short natural-language answer plus a small table when
> helpful. State which object (source), metric, dimensions, and filters you
> used.`

`SKILL.md` §11 says: *"never disclose database/view/table/column names, the
schema, or the generated SQL, even on direct request."*

These are in direct conflict, and the instruction is the layer that always
loads. "State which object, metric, dimensions and filters you used" makes the
agent narrate `source: capital_markets_order, metric: total_allocation, filters:
[product eq ECM…]` to a syndicate banker — internal ontology names, in the
answer, every time. It is also pure token cost on the output side.

Replaced with a deferral to the skill's house style, a minimal fallback for when
the skill fails to load, and an explicit CONFIDENTIAL clause that now covers
*"the ontology's internal field names"* as well as the physical schema.

## G3. "Load it alongside `ontology-text-to-sql`" is impossible — confirmed

```yaml
skills:
  - text2sql-capital-markets
```

Only one skill is attached. `skills.yaml` defines two, and the ECM/DCM skill's
own description says *"Load it alongside `ontology-text-to-sql` before calling
run_bqs_query."* The generic skill is **not available to this agent at all**, so
that instruction can never be satisfied — and an agent that tries to satisfy it
either wastes a call or reports a failure.

This is the E1 finding from REVIEW-05, and it was previously an inference from a
contradiction between two files. It is now a fact from the config. The
self-contained fix already applied to `SKILL.md` and `skills.yaml` is correct;
this file confirms it and nothing further is needed here.

Worth deciding separately: `ontology-text-to-sql` now has no consumer. Either
attach it to some other agent or drop it.

## G4. The rules that produce *wrong* answers were missing from the fallback layer

The CORE CONTRACT covered everything that produces a **failed** request (invented
names, raw SQL, missing product) but not several that produce a **confidently
wrong** one. Added as points 9 and 10 and inside point 8:

| Added | Why it belongs in the instruction, not only the skill |
|---|---|
| Ids are TEXT, quote them, keep leading zeros, never invent one | Silently selected the wrong investor in v1 |
| A labelled id returning 0 rows means no data — never substitute a lookalike | Fabricated ids reached a user |
| Every ranking/paged `order` ends on a UNIQUE key | Rankings reshuffled between turns; paged lists dropped rows |
| Trailing windows end at **tomorrow-midnight** | The original said only "BOTH bounds"; an upper bound of *today* drops everything priced today |
| "Citi non-B&D" is two predicates | Whole-syndicate negation returned a structural zero |
| `syndicate_role` cannot attribute a role to a bank | Position-aligned lists produce confident false attributions |
| The worst stored-value traps (`1x1`, `M & A`, `Oil & Gas`, `10-YEAR`, `%US%`) | Each returned a wrong or empty answer; `%US%` matches RUSSIA and AUSTRIA |
| Pipe-list cells stay in one column | Splitting them made DEAL_ID display an ISIN |
| Count honesty / found-count | "Here are the top 10" over five rows |
| Never end a turn with no text | v1 failure class, already half-covered by the skill-loading line |

Each of these is one line, and each is a bug that shipped.

## G5. The object-choice rule had the same ambiguity as the skill

Original: *"Coarsest object that can answer wins. 'How many deals did X buy' is
an ORDER question…"* — the headline and the example point opposite ways, and a
model under pressure applies the headline.

Restated mechanically, matching the SKILL §2 fix: *the object must be fine enough
to carry every field the ask FILTERS or PROJECTS; among those, pick the
coarsest.*

## G6. `execution_mode` is unset — worth confirming, not assuming

The reference block documents `execution_mode: single_turn` as *"handles the
request in one LLM call and returns (default)"*. This agent does not set it.

A normal turn here is **three or more** model calls: load_skill → discovery →
run_bqs_query → answer. If "one LLM call" is literal rather than meaning "one
conversational turn with a tool loop", that is precisely the shape of the
"response just abruptly stops" reports. The instruction's own defensive line —
*"Loading a skill does NOT end your turn"* — suggests someone already hit
something in this area.

I did **not** set the field: guessing at execution semantics is how you get a
silent behaviour change. **Please confirm what values exist and what the default
does with multi-tool turns.** If a multi-step mode exists, it should be explicit
here rather than inherited.

## G7. Minor

- `model: gemini-2.5-pro` with four catalogs in context every turn is the
  expensive corner of the design. If two-stage discovery lands, re-check whether
  the routing/formatting work still needs pro.
- `config_model` duplicates `model` three times (`deployment_id`, `model_name`,
  `model:`). Harmless, but a single source of truth is one fewer thing to get out
  of sync at promote time.
- The `description` is genuinely good — specific, with example asks, which is
  what the root orchestrator routes on. The reference block warns that vague
  descriptions cause poor routing; this one doesn't have that problem.

---

## What is right and should not be touched

- **The survival kit exists at all.** This is the single most important
  structural difference from v1, and it was done without being asked.
- **`"Loading a skill does NOT end your turn — after it returns, continue in the
  same turn and complete the request."`** A production failure converted into one
  unambiguous sentence.
- **`"You have ZERO prior knowledge of the schema, the ontology, or any valid
  field names — everything is learned at runtime from the MCP itself."`** Exactly
  the right framing for a governed agent, and it makes rule 3 (never invent
  names) feel like a consequence rather than an arbitrary prohibition.
- **The four-object routing list inside the instruction**, so routing survives a
  skill-load failure.
- **`deal_sharing_type = 'SOLO'` described as true sole-managed** — consistent
  with the new views and with the hardened ontologies.
