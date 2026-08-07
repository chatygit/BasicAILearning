# AGENT-V2 — drop-in tree for `176173.fulcrum.ecmo-capmkt-mcp`

This folder mirrors the repo layout. **Copy `adk/`, `app/` and `tests/` over the
repo root and replace.** Nothing here creates a new path the repo does not
already have.

```
adk/config/agents.yaml                     adk/config/skills.yaml
adk/config/tools.yaml                      adk/skills/text2sql-ecm-dcm/SKILL.md
app/config.py                              app/mcpserver.py
app/services/domain_query_service.py
app/bqs/{models,ontology,planner,sql_builder,sql_validator,suggestions,executor,formatter}.py
app/bqs/entity/zen_entity_search.py
app/bqs/ontology/ecm_dcm_{deal,tranche,order,entity}.yaml
tests/test_entitlement_scope.py            (new — no existing file to replace)
```

**`_review/` is ours, not the repo's.** Reviews, the change log, the server
contract notes and the regression gate. Don't copy it.

No `__init__.py` files are included — the repo's own must not be overwritten
with empty ones.

---

## Before you copy

```
python3 _review/ontology_check.py     # 620 checks, exit 0 = safe
```

The ontology loader hot-reloads on mtime, so a YAML dropped into
`app/bqs/ontology/` is **live on the next query with no redeploy**. That makes
this gate the only thing standing between an edit and production — run it every
time.

**These files were transcribed from screenshots. `diff` each against the real
file before replacing it.** The Python carries no provenance comments precisely
so it can be copied as-is, which means this warning only exists here.

## What changed vs. what was transcribed

One behavioural change to server code — `_entitlement_gate` in
`app/mcpserver.py` now intersects the caller's requested product(s) with their
entitlement instead of replacing the filter wholesale.
`tests/test_entitlement_scope.py` is the evidence and runs with no dependencies.

Everything else in `app/` is a faithful transcription plus ordinary engineering
comments (three `FAIL-OPEN (undecided)` markers on entitlement paths, a
`DEPLOYMENT LANDMINE` note on `BQS_ENABLED_SOURCES`, and a `SECURITY` note on
`verify=False` in `zen_entity_search.py`).

The config layer — the four ontologies, `SKILL.md`, `agents.yaml`,
`tools.yaml`, `skills.yaml` — is substantially edited. See
`_review/CHANGES-APPLIED.md`.

## Not included

`app/bqs/dialects/*` (not yet reviewed — `render_literal` on the Trino path is
the one function the read-only guarantee rests on), `app/middleware/*`,
`app/utils/*`, `app/services/entitlement_service.py`, `views/*.sql`, helm.
