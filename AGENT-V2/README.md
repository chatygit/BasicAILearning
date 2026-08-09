# AGENT-V2 — drop-in tree for `176173.fulcrum.ecmo-capmkt-mcp`

This folder mirrors the repo layout. **Copy `adk/`, `app/` and `tests/` over the
repo root and replace.** Nothing here creates a new path the repo does not
already have.

```
adk/config/agents.yaml                     adk/config/skills.yaml
adk/config/tools.yaml                      adk/skills/text2sql-ecm-dcm/SKILL.md
app/config.py                              app/mcpserver.py
app/services/domain_query_service.py       app/services/entitlement_service.py
app/middleware/soeid_middleware.py         app/middleware/auth_middleware.py
app/utils/cyberark_integration/secrets.py
app/bqs/{models,ontology,planner,sql_builder,sql_validator,suggestions,executor,formatter}.py
app/bqs/entity/zen_entity_search.py
app/bqs/ontology/ecm_dcm_{deal,tranche,order,entity}.yaml
tests/test_{entitlement_scope,entitlement_cache,soeid_resolution}.py   (new)
tests/test_{cyberark_cache,disambiguation_scope}.py                    (new)
```

**`_review/` is ours, not the repo's.** Reviews, the change log, the server
contract notes and the regression gate. Don't copy it.

No `__init__.py` files are included — the repo's own must not be overwritten
with empty ones.

---

## Before you copy

```
python3 _review/ontology_check.py     # 775 checks, exit 0 = safe
```

The ontology loader hot-reloads on mtime, so a YAML dropped into
`app/bqs/ontology/` is **live on the next query with no redeploy**. That makes
this gate the only thing standing between an edit and production — run it every
time.

**These files were transcribed from screenshots. `diff` each against the real
file before replacing it.** The Python carries no provenance comments precisely
so it can be copied as-is, which means this warning only exists here.

## What changed vs. what was transcribed

Behavioural changes to server code, each with a dependency-free test:

| file | change |
|---|---|
| `app/mcpserver.py` | `_entitlement_gate` intersects the caller's requested product(s) with their entitlement instead of replacing the filter wholesale |
| `app/mcpserver.py` | identity and entitlement imported under separate flags, so an entitlement import failure no longer presents as `missing_soeid` |
| `app/services/entitlement_service.py` | per-SOEID TTL cache + bounded last-known-good fallback; connection errors and unparseable 200s classified as transient; `reason` kept a stable slug; one pooled session |
| `app/utils/cyberark_integration/secrets.py` | secret cache, so the SecretAgent JVM boots once per FID per TTL rather than once per query |
| `app/bqs/suggestions.py` | the disambiguation probe reuses the main query's WHERE, and returns ids alongside names |
| `app/middleware/auth_middleware.py` | `DISABLE_COIN` normalised; startup warning when auth is off outside local; per-call log demoted to DEBUG |

Everything else in `app/` is a faithful transcription plus ordinary engineering
comments (`FAIL-OPEN (undecided)` markers on entitlement paths, a
`DEPLOYMENT LANDMINE` note on `BQS_ENABLED_SOURCES`, and a `SECURITY` note on
`verify=False` in `zen_entity_search.py`).

**Three fail-open defaults still stack, and none is ours to decide alone:**
`RUN_MODE` defaults to `local` (entitlement gate off), `DISABLE_COIN` defaults
to `true` (no token validated), and an entitlement import failure runs the query
unscoped. All three now say so in the log; none has been flipped, because
flipping any of them without the matching deployment change is an outage.

The config layer — the four ontologies, `SKILL.md`, `agents.yaml`,
`tools.yaml`, `skills.yaml` — is substantially edited. See
`_review/CHANGES-APPLIED.md`.

## Not included

`app/bqs/dialects/*` (not yet reviewed — `render_literal` on the Trino path is
the one function the read-only guarantee rests on), `app/utils/logger.py`,
`app/utils/{auth,exceptions,tracing}.py`, `app/middleware/{metrics,tracing}_middleware.py`,
`views/*.sql`, helm.
