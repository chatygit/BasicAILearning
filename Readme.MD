# ADK-KIT — ECM/DCM capital markets text-to-SQL

Two architectures for the same problem: answering natural-language questions
about ECM (Equity Capital Markets) and DCM (Debt Capital Markets) deal,
tranche, order and allocation data on Citi's Ask Banking platform.

| folder | what | status |
|---|---|---|
| **`AGENT-V2/`** | BQS ontology. The agent emits a governed **Business Query Specification**; the MCP compiles the SQL. Four grain-aligned objects: `ecm_dcm_deal`, `ecm_dcm_tranche`, `ecm_dcm_order`, `ecm_dcm_entity`. | **The plan going forward.** |
| `V1/` | The shipped text2sql agent + `text2sql_mcp`, where the agent writes the SQL. | Reference only. |

## Working in AGENT-V2

Mirrors the `176173.fulcrum.ecmo-capmkt-mcp` repo layout, so the folder can be
copied over the repo and replace files in place.

```
adk/config/{agents,skills,tools}.yaml    local ADK runtime config
adk/skills/text2sql-ecm-dcm/SKILL.md     the skill
app/…                                    MCP server: bqs/, middleware/, services/
tests/                                   runnable, dependency-free
_review/                                 NOT copied to the repo — gate, reviews, V1 reference
```

Everything under `adk/`, `app/` and `tests/` is copy-over material. `_review/`
is ours and never ships.

**Run the gate before handing anything back:**

```bash
cd AGENT-V2 && python3 _review/ontology_check.py
```

`_review/mcp_probe.py` diagnoses a deployed MCP server — health, transport shape
(405 stateless vs 406 stateful), session creation, and how many tools it
actually registers. Point it at a working environment and a failing one; the
first row that differs is the cause.

## Promotion

Local ADK reads `adk/config/*`. Higher environments do **not** — there the agent,
skills and MCP toolset are created in the Ask Banking onboarding UI, and
promoting means copying the agent description and instructions into that UI by
hand. `adk/config/tools.yaml` is local-only and cannot shadow the registry.

## Standing constraints

- `VW_DEAL_ORDER_SUMMARY` is **not ours to change.** Findings go to the data
  team and QA raises them; a view change needs the SOLO-vs-SHARED conversation.
  Our job is to query it correctly and efficiently.
- `PRODUCT` keeps its name.
- Never mix units: ECM sizes and allocations are **share counts**, DCM is
  notional **money**. Always scope one product; DCM money needs one currency.
