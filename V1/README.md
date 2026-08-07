# V1 — text2sql agent (reference only)

The shipped V1 architecture: a Google ADK agent plus the `text2sql_mcp` server
(`plexus-ai-core.mcp-nl2sql-server`), where the agent writes SQL from schema
context the MCP hands back.

**Not the plan going forward — see `../AGENT-V2/`.** V1 is kept because it is
the working reference: when V2 misbehaves in an environment where V1 does not,
the answer is usually a diff against these files.

Only the latest revision of each file is here. Superseded numbered versions
(`agents.yml`..`agents-v5.yml`, `skill.md`..`skill-v6.md`, `domain.yml`,
`domain-v2.yml`, and the earlier `column-intent` / `fast-path` / `follow-ups` /
`fuzzy` / `unspported` / `vw_deal_order_summary` / `sql-validation` files) were
deleted in the V1 cleanup. They remain in git history.

## Layout

| path | what |
|---|---|
| `regression_check.py` | **206-check gate. Run before any V1 promote.** |
| `agent/` | ADK side: `agents-v6.yml` (static instruction), `skill-v7.md`, `skills.yml`, `tools.yml`, and the sub-agent definitions |
| `domain/` | `domain-v4.yml`, `sql-validation-v2.yml`, `vw_deal_order_summary-v3.json` (view schema), `dictionary-official.md` |
| `domain/criteria/` | the JSON criteria files the MCP loads: broker aliases, column intent/priority, fast paths, follow-ups, fuzzy scenarios, unsupported intents |
| `mcp/` | MCP-side Python: `text2sql-current.py`, helpers, `entitlement_service-current.py`, surgical-change notes |
| `docs/` | `PROMOTE-CHECKLIST.md`, the BQS 4-view spec, view-split proposal, QA findings for the data team, scope notes |
| `reference/` | captured structure and traces: folder listings, architecture notes, `columns.txt`, `trace.txt`, diagnostics SQL |

## Running the gate

```bash
python3 V1/regression_check.py          # -v for per-check detail
```

It resolves `agent/skill-v7.md`, `agent/agents-v6.yml`, `domain/domain-v4.yml`,
`domain/vw_deal_order_summary-v3.json`, `domain/sql-validation-v2.yml` and
`domain/criteria/unspported-v2.json` relative to its own location. Moving any of
those six means updating the path constants at the top of the script.

## Standing constraints (unchanged from V1)

- `VW_DEAL_ORDER_SUMMARY` is **not ours to change**. Findings go to the data
  team; QA raises them. A view change requires the SOLO-vs-SHARED conversation.
- Our job is to query the view correctly and efficiently for the prompts.
- `PRODUCT` keeps its name.
