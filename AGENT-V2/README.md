# AGENT-V2 — drop-in tree for `176173.fulcrum.ecmo-capmkt-mcp`

This folder mirrors the repo layout. **Copy `adk/`, `app/` and `tests/` over the
repo root and replace.** Nothing here creates a new path the repo does not
already have.

```
adk/config/agents.yaml                     adk/config/skills.yaml
adk/config/tools.yaml                      adk/skills/text2sql-capital-markets/SKILL.md
app/config.py                              app/mcpserver.py
app/services/domain_query_service.py       app/services/entitlement_service.py
app/middleware/soeid_middleware.py         app/middleware/auth_middleware.py
app/utils/cyberark_integration/secrets.py
app/bqs/{models,ontology,planner,sql_builder,sql_validator,suggestions,executor,formatter}.py
app/bqs/entity/zen_entity_search.py
app/bqs/ontology/capital_markets_{deal,tranche,order,entity}.yaml
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

**The `RUN_MODE` bypass is gone.** `_ecm_entitlement_enabled()` no longer
consults the run mode, so the gate behaves identically on a laptop and in QA.
`ECM_DCM_ENTITLEMENT_FEATURE_FLAG` is the only switch. A local run therefore
needs that flag set to `false` **or** real ECMO credentials — see the note in
`adk/config/tools.yaml`. Gated by 2 checks, one of which fails if the helper
returns at all.

**Two fail-open defaults remain, and neither is ours to decide alone:**
`DISABLE_COIN` defaults to `true` (no token validated), and an entitlement
import failure runs the query unscoped. Both now say so in the log; neither has
been flipped, because flipping either without the matching deployment change is
an outage.

**Three entitlement env vars are new and not in the chart.** All have working
defaults, so nothing breaks without them; add them only if you want them tunable
per environment. They belong inside the existing `{{- with .Values.ecmDcm }}`
block in the deployment template, beside `ECM_DCM_ENTITLEMENT_POLICY_ID`:

```yaml
- name: ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS
  value: {{ .entitlementCacheTtlSeconds | default "300" | quote }}
- name: ECM_DCM_ENTITLEMENT_STALE_MAX_AGE_SECONDS
  value: {{ .entitlementStaleMaxAgeSeconds | default "3600" | quote }}
- name: ECM_DCM_ENTITLEMENT_TIMEOUT_SECONDS
  value: {{ .entitlementTimeoutSeconds | default "30" | quote }}
```

The stale bound is the one with a security argument: it caps how long a revoked
user keeps their scope while the ECMO API is unreachable.

**Startup now states the entitlement posture on one line.** The chart ships
`entitlementFeatureFlag: "false"` with an empty `productEntitlementUrl` and
`entitlementPolicyId`, so flipping the flag alone refuses **every** query with
`entitlement_misconfigured`. That is now an ERROR at pod start rather than a
discovery on the first user query.

The config layer — the four ontologies, `SKILL.md`, `agents.yaml`,
`tools.yaml`, `skills.yaml` — is substantially edited. See
`_review/CHANGES-APPLIED.md`.

## Not included

`app/bqs/dialects/*` (not yet reviewed — `render_literal` on the Trino path is
the one function the read-only guarantee rests on), `app/utils/logger.py`,
`app/utils/{auth,exceptions,tracing}.py`, `app/middleware/{metrics,tracing}_middleware.py`,
`views/*.sql`, helm.
