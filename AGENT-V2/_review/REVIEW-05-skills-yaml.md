# Review 05 — `adk/config/skills.yaml`

Two skills declared, both bound to `text_to_sql_mcp`:

| Skill | Purpose |
|---|---|
| `ontology-text-to-sql` | generic: discover first, never invent field names, never write raw SQL, submit structured BQS, surface governance rejections |
| `text2sql-ecm-dcm` | domain: maps business language onto the four grain-aligned objects, routing by grain, units, B&D, house answer style |

Small file, but it raises the biggest open question of the migration.

---

## E1. The two files contradict each other on self-containment

- `SKILL.md` front matter: *"It is **self-contained** — it includes the full
  discover→run contract."*
- `skills.yaml` description: *"**Load it alongside** `ontology-text-to-sql` before
  calling `run_bqs_query`."*

Both cannot be true. Either the ECM/DCM skill carries the contract (and the generic
skill is redundant token cost on every ECM/DCM turn), or it does not (and the front
matter is wrong).

Given §0 of `SKILL.md` does spell out the discover→run loop, self-contained looks
correct — in which case the ECM/DCM path should not load the generic skill at all.
Pick one and make both files agree.

## E2. A hard dependency between two skills, with no mechanism to enforce it

The dependency lives in prose inside a `description`. There is no `requires:` /
`depends_on:` in the visible schema.

This matters because of a v1 lesson: **skill loading was discretionary**, and
skill-absent turns were a real failure class — we proved it from token counts
(baselines below the skill's own size). We compensated by inlining the critical rules
into the agent instruction as a "survival kit".

With two skills, the failure surface doubles: a turn can now have skill A, skill B,
both, or neither, and the prose dependency is invisible to the loader.

Questions: **is skill loading eager or discretionary for this agent?** If discretionary,
either merge the two (E1 suggests that anyway) or confirm the framework can express a
dependency. If it cannot, the survival-kit approach still applies — the handful of
rules that must never be missing belong in the agent instruction.

## E3. Does `discover_business_terms()` return all four catalogs? — this decides the token case

`SKILL.md` §0: *"`discover_business_terms()` FIRST — it returns **the FOUR sources**
with their `grain` and catalogs."*

If that means all four full catalogs (metrics + dimensions + filters + operators +
`how_to_use` + `usage_notes` + `examples`) in one response, then discovery ships
**more** than v1's single 7k-token schema — because the four objects together have more
fields than the one view did, plus four sets of prose.

The token argument in the migration proposal (~330k → ~120k per ask) assumed
**grain-routed delivery**: ship only the catalog for the object the ask needs. Without
that, the per-hop context could go *up*, not down — and per-hop context is now a
reliability issue as well as a cost one (we measured an empty-candidate `STOP` at
91,676 prompt tokens in v1).

**Suggested shape — two-stage discovery:**

1. `discover_business_terms()` with no argument returns a **thin index**: four source
   names, their `grain`, and one routing line each (~200 tokens total).
2. `discover_business_terms(source="ecm_dcm_order")` returns the **full catalog** for
   that object only.

§2 routing already gives the agent everything it needs to pick from the thin index, so
the second call is well-targeted. If the tool already supports a `source` argument,
`SKILL.md` §0 should say "discover the index, pick the object, then discover that
object" rather than implying one fat call.

**Please measure:** the `promptTokenCount` on a v2 turn, same as we did for v1. That
single number tells us whether the architecture delivered its main promise.

## E4. Neither skill uses `tool_filter`

The template documents `tool_filter: ["search", "lookup"]` to restrict which tools of a
toolset a skill may call. Both skills take all of `text_to_sql_mcp`.

If the toolset exposes tools this agent should never call, filtering reduces both the
error surface (fewer wrong-tool calls) and the tool-definition tokens carried every
turn. Worth checking what `text_to_sql_mcp` actually exposes — if it is exactly
`discover_business_terms` + `run_bqs_query`, no action needed.

## E5. Minor

- `metadata: {}` is unused on both. It could carry the ontology version (`"2"`) so a
  trace shows which generation of the catalog answered — useful when v1 and v2 run side
  by side during migration.
- Naming is inconsistent between `ontology-text-to-sql` and `text2sql-ecm-dcm`
  (`text-to-sql` vs `text2sql`). Cosmetic, but the skill `name` must match its
  directory, so it is worth being deliberate.

---

## What is right

- The ECM/DCM skill's description is explicitly **routing-first** ("which object
  answers which ask (routing by grain)") — it advertises the decision the agent has to
  make before anything else.
- "LOAD FIRST … REQUIRED to answer correctly" is the right level of insistence for a
  skill the answer depends on.
- Tags are specific enough (`ecm`, `dcm`, `capital-markets`) to support filtering if the
  agent roster grows.
- The template's note that **MCP connections are lazy — no extra latency at bootstrap**
  is worth knowing: binding the toolset to both skills costs nothing at startup.
