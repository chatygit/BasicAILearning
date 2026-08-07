# Review 08 — `app/mcpserver.py`

Two tools, an entitlement gate, and one correction to something I told you twice.

---

## H1. I was wrong: `discover_business_terms` IS scopeable

```python
@mcp.tool()
def discover_business_terms(source: str | None = None) -> dict:
    """...
    Args:
        source: Optional business data source name. If omitted, returns the
            catalog for ALL enabled sources — read each source's 'how_to_use'
            and 'usage_notes' to pick the right one for the question.
    """
    return _get_bqs_service().discover(source)
```

I said discovery *"takes no arguments"* and *"is not scopeable"*, and I wrote
that into REVIEW-07, `CHANGES-APPLIED.md` and memory. It was inference from two
places that describe the *call site*, not the *signature*: the agent instruction
says `FIRST (no arguments)`, and `tools.yaml` never mentioned the parameter. Both
have been corrected.

**This turns the biggest open item from "needs a server change" into a
config-only fix, available now.**

The agent already knows the four object names and what each answers — that
routing list is in `static_instruction` rule 2 and in SKILL §2. So it can choose
the object *without any tool call*, then fetch **one** catalog:

```
discover_business_terms(source="ecm_dcm_order")
```

That is the two-stage design, with the "thin index" being the routing table we
already ship. Applied to `agents.yaml` rule 1, SKILL §0 and the tool description.

Cost of a wrong pick: one extra scoped call — still far cheaper than fetching
four catalogs on every turn, forever.

Note also `stateless_http=True` on the app: there is **no server-side session**,
so whether discovery fires once or every turn is purely agent behaviour. The
"per-SESSION knowledge, never re-fetch" line is the only lever, and it is now in
both the instruction and the skill.

## H2. The entitlement gate discards the user's product filter — this re-opens the units bug

```python
# Bound the query to the entitled product(s): drop any pre-existing product
# filters and inject a single governed one scoped to the entitlement.
filters = [f for f in (request.get("filters") or [])
           if str(f.get("field", "")).strip().lower() != "product"]
if len(entitled) == 1:
    filters.append({"field": "product", "op": "eq", "value": entitled[0]})
else:
    filters.append({"field": "product", "op": "in", "value": entitled})
request["filters"] = filters
```

The gate computes `requested` (what the user asked for) a few lines earlier, uses
it **only** to decide whether to deny, and then throws it away.

**Consequence for a user entitled to both ECM and DCM — which is the normal
case:**

| | |
|---|---|
| User asks | "Total deal size for ECM deals in 2025" |
| Agent sends | `filters: [{product, eq, ECM}, …]` |
| Gate rewrites to | `filters: [{product, in, [ECM, DCM]}, …]` |
| Query returns | ECM **and** DCM |
| `total_deal_size` becomes | ECM share counts **summed with** DCM notional money |

That is the "1,000.0bn shares" failure, injected by the server, after every
guard we put in the ontology. `requires_filters: [product]` is satisfied — a
product filter *is* present — it is just not the one the agent asked for. The
agent cannot detect it, cannot prevent it, and will label the number with
whichever unit it thinks it scoped to.

It also silently widens every non-aggregate answer: "list ECM deals" returns
bonds.

**Fix — intersect rather than replace:**

```python
scope = [p for p in requested if p in entitled] or entitled
if len(scope) == 1:
    filters.append({"field": "product", "op": "eq", "value": scope[0]})
else:
    filters.append({"field": "product", "op": "in", "value": scope})
```

Entitlement still binds — `requested` was already validated against `entitled`
above, and an empty `requested` still falls back to the full entitlement. The
only behaviour that changes is that an explicit, permitted product scope
survives.

**This is the highest-value finding in the v2 review so far.** It needs a server
change; no config edit can work around it.

## H3. Three fail-open paths in the same gate

```python
if not _ENTITLEMENT_AVAILABLE:
    return None                      # (a) import failed → no gate at all
...
if not entitled:
    return None  # gate said ok but no products - let the query proceed unscoped
```

- **(a)** If `services.entitlement_service` or `middleware.soeid_middleware`
  fails to import, the gate is skipped entirely and every query runs unscoped.
  It logs a warning at startup and nothing at request time.
- **(b)** A caller the gate approves but who has **no** ECM/DCM products gets an
  **unscoped** query — all products, by an explicit code comment.
- **(c)** `_is_local_mode()` reads `os.getenv("RUN_MODE", "local")` — the
  **default is local**, and local mode returns `False` from
  `_ecm_entitlement_enabled()`. So entitlement is **off unless the deployment
  explicitly sets `RUN_MODE` to something non-local**.

You reported in v1: *"I only have ECM entitlements and I was able to see DCM
data."* Any of (a), (b), (c) — or H2 — produces exactly that.

Worth deciding deliberately, since all three are currently "allow": should an
unavailable gate, an entitled-but-productless caller, or an unset `RUN_MODE`
**fail closed** on a production deployment? For a Citi entitlement boundary the
usual answer is yes, with local mode the single explicit exception. At minimum
`RUN_MODE` belongs on the promote checklist.

## H4. Auto-discovery would expose a third tool — pinning was right

The server registers `tool_echo_user_context` (a diagnostic that returns the
resolved SOEID) alongside the two BQS tools. With `mcp_tool_names: []` the agent
would be offered all three, plus whatever is added later.

The pin to `[discover_business_terms, run_bqs_query]` in `tools.yaml` was
speculative when I made it; it is now justified by evidence. A diagnostic that
echoes caller identity is not something the agent should be able to call.

## H5. The server's docstring settles the B&D `[VERIFY]` — and it matches

```
computed_filters: List of {"name", "token"} governed computed filters.
    Pass a business token like "citi"; omit token for token-less filters.
    Add "negate": true to match rows that do NOT satisfy it - e.g.
    "non-B&D" = bill_and_deliver with negate, "Citi non-B&D" =
    syndicate_member "citi" plus bill_and_deliver with negate.
```

`bill_and_deliver` is **token-less**, and the server documents the composite
recipe in the same words we arrived at. My version passed a token to it; that is
now corrected in the tranche object, SKILL §7 and the agent instruction to match
the server exactly.

Also confirmed here: `derived_filters` is a list of **names** (strings), `having`
takes `{metric, op, value}`, `limit` is *"clamped to the source's max_limit"* —
so `max_limit: 5000` in the ontologies is a real ceiling, not advice.

## H6. Minor

- The `run_bqs_query` docstring already carries a compact version of the house
  patterns (one metric, top-N shape, calendar year as two filters, read
  `suggestions`/`did_you_mean`/`disambiguation`). Belt-and-braces with the skill,
  and it ships on every request — good.
- `FastMCP(instructions="Starter Helix server for MCP. Shows examples of MCP
  components: Tool, Resource and Prompt.")` is still the template default. It is
  server-level text some clients surface; worth replacing with a real
  description.
- `get_user_profile` and `analyze_data` are template sample resource/prompt
  components. Harmless, but they are demo scaffolding in a governed server.
- `_resolve_soeid()` falls back to `LOCAL_DEFAULT_SOEID` (default `"sr37832"`)
  in local mode only — correct shape for a dev bypass.

---

## What changed in our files

| Change | Why |
|---|---|
| `agents.yaml` rule 1 → pick the object, then `discover_business_terms(source=…)` | H1 — one catalog instead of four |
| SKILL §0 restructured to object-first, scoped discovery | H1 |
| `tools.yaml` description now names the four sources and the `source` argument | H1 — the tool description is the layer that always loads |
| B&D recipe → `syndicate_member 'citi'` + token-less `bill_and_deliver` negate | H5 — matches the server verbatim |
| SKILL §8 handles `entitlement_denied` / `product_not_entitled` | H2/H3 — these codes reach the agent |

## What goes back to the POC team

1. **H2 — the product-filter override.** One-line fix, and it is currently
   producing wrong numbers for every dual-entitled user.
2. **H3 — decide the three fail-open paths**, and put `RUN_MODE` on the promote
   checklist.
3. `requires_filters` enforcement — still unseen; `planner.py` next.
