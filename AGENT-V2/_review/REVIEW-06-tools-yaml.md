# Review 06 — `adk/config/tools.yaml`

One toolset, `text_to_sql_mcp`, exposing `discover_business_terms` and
`run_bqs_query`. Short file, two findings that matter, one of which is the most
useful realisation of this whole review pass.

---

## F1. The tool contract confirms the discovery-payload concern

The description states `discover_business_terms` *"lists the FOUR grain-aligned
objects — deal, tranche, order, entity — each with its `grain`, metrics,
dimensions, and filters"*. No `source` argument is mentioned.

Taken literally that is **all four catalogs on every discovery call**. The deal
object alone is ~250 lines of YAML; four of them, plus `how_to_use`,
`usage_notes` and `examples`, is plausibly 10–15k tokens.

This is the migration's central assumption, so it should be measured rather than
assumed. Two numbers settle it:

1. `promptTokenCount` on a simple v2 turn (the same field that showed **91,676**
   on v1 and correlated with an empty-candidate `STOP`).
2. Whether discovery is called **once per session** or **once per turn**. Once per
   session is far better — but the payload then persists in conversation for every
   subsequent hop, which is exactly the accumulation that took v1 from ~35k to
   ~92k.

If it is one fat call, the fix is two-stage discovery: a thin index (four names +
`grain` + one routing line each, ~200 tokens), then the full catalog for the
chosen object only. §2 of `SKILL.md` already gives the agent everything it needs
to pick from the index. The MCP server's actual tool schema — not this file —
will say whether `source` is already accepted; that is the last artefact I need.

## F2. The tool description IS the real survival kit — use it deliberately

This is worth stating plainly because it changes where the critical rules belong.

In v1 we learned that **skill loading is discretionary**, and compensated by
inlining must-never-be-missing rules into the agent instruction. In this
architecture there is something even more reliable: **tool definitions ship with
every single request**, regardless of which skills loaded, how long the
conversation is, or whether the agent read the catalog.

The description already carries the single most important rule —
*"Pick the object by the grain of the thing being counted/listed"* — which is
exactly right. It has room for the two or three others whose absence produces a
**wrong answer rather than a failed one**:

- always scope `product` (ECM or DCM) on every request
- never total sizes/allocations/demand across products — ECM is share counts, DCM
  is money
- ids are text; quote them

Everything else can live in the skill or the catalog. But those three, plus the
grain rule, are the ones where a silently-wrong answer is the failure mode, and
this is the only text guaranteed to be present.

## F3. `mcp_tool_names: []` auto-discovers whatever the server exposes

For a governed, read-only system, pinning the list is cheap insurance:

```yaml
mcp_tool_names: ["discover_business_terms", "run_bqs_query"]
```

Auto-discovery means a tool added to the MCP server later is silently granted to
this agent with no config change and no review. Pinning also makes the tool
surface auditable from config alone — useful when the whole point of the design
is that the server governs what the agent may do.

## F4. Minor

- `mcp_server_url` defaults to `http://localhost:8095/mcp`. Fine for the POC; make
  sure the deploy checklist sets `TEXT_TO_SQL_MCP_URL` explicitly rather than
  relying on the default.
- No `tool_name_prefix` — correct while there is a single MCP server; worth
  remembering if a second one is ever attached, since both could expose a
  `discover_*` tool.

---

## What is right

- **Read-only is stated in the tool description itself.** A model reading only the
  tool list already knows it cannot mutate anything.
- **"ALWAYS call first"** on `discover_business_terms` — the contract is enforced
  at the layer that is always present.
- **"runs a structured Business Query Specification against ONE object; you never
  write raw SQL"** — the one-object constraint is stated at the tool boundary, not
  just in the skill, so the no-joins design is visible even without the skill.
- Environment-variable substitution for the URL rather than a hardcoded endpoint.
