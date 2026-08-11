#!/usr/bin/env python3
"""
V2 ontology regression check — the AGENT-V2 counterpart of regression_check.py.

Run it before handing these files back to the POC repo. Exit 0 = safe.

It is deliberately dependency-free (no PyYAML): checks are text/structural, in
the same style as the v1 suite, so it runs anywhere the repo is checked out.

Every check encodes a failure that ACTUALLY HAPPENED in v1 production or QA.
When a new class of bug is fixed, add a check here — that is the whole point.
"""
import re
import sys
from pathlib import Path

# This script lives in _review/; everything it checks lives in the repo-shaped
# tree one level up (adk/... and app/...), so paths mirror the real repo.
ROOT = Path(__file__).parent.parent
ONT = ROOT / "app" / "bqs" / "ontology"
DEAL = ONT / "capital_markets_deal.yaml"
TRANCHE = ONT / "capital_markets_tranche.yaml"
ORDER = ONT / "capital_markets_order.yaml"
ENTITY = ONT / "capital_markets_entity.yaml"
SKILL = ROOT / "adk" / "skills" / "text2sql-capital-markets" / "SKILL.md"
TOOLS = ROOT / "adk" / "config" / "tools.yaml"
SKILLS = ROOT / "adk" / "config" / "skills.yaml"
AGENTS = ROOT / "adk" / "config" / "agents.yaml"

OBJECTS = [DEAL, TRANCHE, ORDER, ENTITY]

# Columns whose UNIT depends on PRODUCT (ECM = share counts, DCM = money).
# Any aggregate over one of these must be product-scoped or it adds shares to
# dollars. This is the "1,000.0bn shares" bug.
UNIT_BEARING = {
    "deal_size", "tranche_size",
    "order_allocation", "order_demand_qty", "order_amount",
    "syndicate_member_name",   # list_count is ECM-only; DCM exposes one member
}

# Aggregations that are meaningless across mixed units. COUNT_DISTINCT is fine.
UNIT_SENSITIVE_AGGS = {"SUM", "MAX", "MIN", "AVG"}

# A ranking/paged 'order' must END on a key that is unique AT THE RESULT GRAIN —
# i.e. unique among the groups the request projects, not necessarily the base
# grain. "Top investors" groups by investor, so investor_id is the right
# tiebreaker; order_id is not even available there.
def is_unique_at_grain(field, dims):
    if field not in dims:
        return False                     # cannot sort on an unprojected field
    if len(dims) == 1:
        return True                      # the sole group key is unique per row
    return field.endswith("_id")         # an id among the group keys

failures = []
passes = 0


def check(condition, label, detail=""):
    global passes
    if condition:
        passes += 1
    else:
        failures.append(f"{label}" + (f"\n      {detail}" if detail else ""))


def text(path):
    return path.read_text()


def has(path, phrase):
    """Case-insensitive presence. Rewrites recase prose; behaviour is what matters."""
    return phrase.lower() in text(path).lower()


def blocks(path, section):
    """Yield (name, body) for each 2-space-indented key under `section:`."""
    src = text(path)
    m = re.search(rf"^{section}:\s*$", src, re.M)
    if not m:
        return
    rest = src[m.end():]
    end = re.search(r"^\S", rest, re.M)
    rest = rest[: end.start()] if end else rest
    for bm in re.finditer(r"^  ([a-z_0-9]+):\s*(.*?)(?=^  [a-z_0-9]+:|\Z)", rest, re.M | re.S):
        yield bm.group(1), bm.group(2)


# ---------------------------------------------------------------------------
# 0. YAML SHAPE — a prose list item containing ": " parses as a MAPPING, not a
#    string, so `usage_notes: list[str]` fails validation and the WHOLE source
#    silently fails to load. This is valid YAML, so a plain parse check misses
#    it entirely; only the type matters. Cost us the capital_markets_entity source.
# ---------------------------------------------------------------------------
PROSE_LISTS = ("usage_notes", "how_to_use")
for path in OBJECTS:
    src = text(path)
    for key in PROSE_LISTS:
        m = re.search(rf"^{key}:\s*$", src, re.M)
        if not m:
            continue
        rest = src[m.end():]
        end = re.search(r"^\S", rest, re.M)
        block = rest[: end.start()] if end else rest
        for im in re.finditer(r"^  - (.*)$", block, re.M):
            item = im.group(1)
            if item[:1] in ("'", '"', "|", ">", "{", "["):
                continue                      # quoted or explicitly structured
            line = src[: m.end() + im.start()].count("\n") + 1
            check(not re.search(r"[^\s]: ", item),
                  f"[yaml] {path.name}:{line}: '{key}' item is unquoted and "
                  f"contains ': ', so YAML parses it as a MAPPING",
                  f"Quote the whole item. Item: {item[:70]}...")

# ---------------------------------------------------------------------------
# 0b. REFERENTIAL INTEGRITY — never instruct the agent to use a governed name
#     the server cannot resolve. planner._resolve_computed_filter raises
#     `unknown_computed_filter` for anything not in spec.computed_filters, so a
#     recipe naming an undeclared filter fails at RUNTIME, not at load. The
#     four-view split dropped v1's computed_filters block while the skill, the
#     agent instruction and a worked example all still called for it.
# ---------------------------------------------------------------------------
V1_COMPUTED = ["broker_participation", "syndicate_member", "bill_and_deliver",
               "syndicate_role_lead"]
declared_cf = set()
for path in OBJECTS:
    for name, _body in blocks(path, "computed_filters"):
        declared_cf.add(name)

# (a) no request example may name an undeclared computed filter
for path in OBJECTS:
    src = text(path)
    for m in re.finditer(r"^\s*-\s*\{name:\s*([a-z_0-9]+)", src, re.M):
        line = src[: m.start()].count("\n") + 1
        check(m.group(1) in declared_cf,
              f"[refint] {path.name}:{line}: example uses computed_filter "
              f"'{m.group(1)}', which no ontology declares",
              "planner raises unknown_computed_filter — the example cannot run.")

# (b) the skill and the agent instruction may only *recommend* one that exists,
#     unless they explicitly say it is unavailable
for path in [SKILL, AGENTS]:
    src = text(path)
    for name in V1_COMPUTED:
        if name in declared_cf:
            continue
        # Word-boundary match: `syndicate_member_name` is a REAL filter and must
        # not be mistaken for the computed filter `syndicate_member`.
        for m in re.finditer(rf"{re.escape(name)}(?![a-z_])", src):
            raw = src[max(0, m.start() - 500): m.end() + 500]
            window = " ".join(re.sub(r"[`*]", "", raw).split())
            line = src[: m.start()].count("\n") + 1
            check(re.search(r"NOT available|not available|unknown_computed_filter|"
                            r"declares no computed_filters|declare NO computed_filters",
                            window, re.I) is not None,
                  f"[refint] {path.name}:{line}: recommends computed_filter "
                  f"'{name}', which no ontology declares, without saying it is "
                  f"unavailable",
                  "Either port the computed_filters block or stop recommending it.")

# ---------------------------------------------------------------------------
# 1. UNITS GUARD — every unit-sensitive aggregate declares requires_filters
# ---------------------------------------------------------------------------
for path in OBJECTS:
    for name, body in blocks(path, "metrics"):
        col = re.search(r"column:\s*(\S+)", body)
        agg = re.search(r"aggregation:\s*(\S+)", body)
        if not col or not agg:
            continue
        if col.group(1) in UNIT_BEARING and agg.group(1) in UNIT_SENSITIVE_AGGS:
            check(
                "requires_filters" in body and "product" in body,
                f"[units] {path.name}: metric '{name}' aggregates {col.group(1)} "
                f"with {agg.group(1)} but has no requires_filters: [product]",
                "ECM is share counts, DCM is notional money — this is the "
                "'1,000.0bn shares' failure.",
            )

# ---------------------------------------------------------------------------
# 2. TIEBREAKERS — every example 'order:' ends on a key unique at its grain
# ---------------------------------------------------------------------------
for path in OBJECTS:
    src = text(path)
    for ex in re.split(r"^  - question:", src, flags=re.M)[1:]:
        om = re.search(r"^\s*order:\s*(\[.*?\])\s*$", ex, re.M | re.S)
        if not om:
            continue
        fields = re.findall(r"field:\s*([a-z_0-9]+)", om.group(1))
        dm = re.search(r"dimensions:\s*\[(.*?)\]", ex, re.S)
        dims = [d.strip() for d in dm.group(1).split(",")] if dm else []
        title = ex.strip().splitlines()[0][:60]
        if not fields:
            continue
        check(
            is_unique_at_grain(fields[-1], dims),
            f"[tiebreak] {path.name} — \"{title}\": order ends on "
            f"'{fields[-1]}', which is not unique among the projected "
            f"dimensions {dims}",
            "Ties reshuffle between turns; paged listings repeat or drop rows.",
        )

# ---------------------------------------------------------------------------
# 2a. OPERATOR WHITELIST — verbatim from app/bqs/models.py FilterOperator.
#     Declaring an operator the compiler does not implement is a runtime
#     rejection dressed up as governance. NOTE: there is no not_like — negation
#     of broker/syndicate/B&D logic goes through computed_filters + negate.
# ---------------------------------------------------------------------------
VALID_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in",
             "between", "like", "is_null", "is_not_null"}
for path in OBJECTS:
    src = text(path)
    for m in re.finditer(r"operators:\s*\[([^\]]*)\]", src):
        for op in [o.strip() for o in m.group(1).split(",") if o.strip()]:
            line = src[: m.start()].count("\n") + 1
            check(op in VALID_OPS,
                  f"[operator] {path.name}:{line}: '{op}' is not a "
                  f"FilterOperator the server implements",
                  f"Valid: {' '.join(sorted(VALID_OPS))}")
    for m in re.finditer(r"op:\s*([a-z_]+)", src):
        check(m.group(1) in VALID_OPS,
              f"[operator] {path.name}: example uses op '{m.group(1)}', which "
              f"is not a FilterOperator the server implements")
# `not_like` may only appear while being ruled OUT. Actual usage is caught by
# the operators-list and op: checks above; here we assert the teaching survives,
# because "use not_like" is the intuitive wrong answer a rewrite drifts back to.
for path in [TRANCHE, SKILL, AGENTS]:
    for m in re.finditer(r"not_like", text(path)):
        # Normalise: YAML folded scalars wrap these phrases across lines, and
        # markdown puts backticks/asterisks in the middle of them.
        raw = text(path)[max(0, m.start() - 140): m.end() + 140]
        window = " ".join(re.sub(r"[`*]", "", raw).split())
        check(re.search(r"no not_like|not_like operator|does not exist|"
                        r"NOT a FilterOperator", window, re.I) is not None,
              f"[operator] {path.name}: 'not_like' used as if it were a real "
              f"operator — it is not in FilterOperator; use a computed_filter "
              f"with negate")
    check(has(path, "not_like"),
          f"[operator] {path.name}: lost the 'there is no not_like' warning — "
          f"it is the intuitive wrong answer for every NOT-a-bank ask")

# ---------------------------------------------------------------------------
# 2b. OPERATOR/VALUE COHERENCE — IN does not honour wildcards, and filters are
#     ANDed, so an OR of two like-patterns is not expressible. A pattern list
#     under `in` silently matches nothing.
# ---------------------------------------------------------------------------
for path in OBJECTS:
    src = text(path)
    for m in re.finditer(r"op:\s*(in|not_in),\s*value:\s*\[([^\]]*)\]", src):
        if "%" in m.group(2):
            line = src[: m.start()].count("\n") + 1
            check(False,
                  f"[operator] {path.name}:{line}: '{m.group(1)}' given wildcard "
                  f"patterns [{m.group(2)}]",
                  "IN compares literals — the wildcards match nothing. Use a "
                  "single 'like' on the token the view actually stores.")
for path in OBJECTS + [SKILL]:
    check(not re.search(r"like\s+'%[^']*%'\s+OR\s+", text(path)),
          f"[operator] {path.name}: instructs an OR of predicates, which ANDed "
          f"filters cannot express")

# ---------------------------------------------------------------------------
# 2d. COMPILER REQUIREMENTS (from sql_builder.py).
#     _agg_expr casts only when numeric=True: "Value aggregations
#     (SUM/AVG/MIN/MAX) require a numeric argument. Cast when the governed
#     measure is stored as text (e.g. Trino VARCHAR columns)." TRANCHE_SIZE was
#     exactly that mismatch in v1. list_count metrics are exempt — that path
#     passes numeric=False deliberately.
# ---------------------------------------------------------------------------
VALUE_AGGS = {"SUM", "AVG", "MIN", "MAX"}
for path in OBJECTS:
    for name, body in blocks(path, "metrics"):
        agg = re.search(r"aggregation:\s*(\S+)", body)
        if not agg or agg.group(1) not in VALUE_AGGS:
            continue
        if "list_count" in body:
            continue
        check("numeric: true" in body,
              f"[cast] {path.name}: metric '{name}' is a {agg.group(1)} without "
              f"numeric: true — no numeric_cast is emitted, so it misbehaves on "
              f"a VARCHAR-backed column")

# HAVING is rejected on a deduplicated metric ("plain path only; the planner
# rejects HAVING combined with a deduplicated metric"). Our examples rely on it.
for path in OBJECTS:
    src = text(path)
    dedup_metrics = {n for n, b in blocks(path, "metrics") if "dedup_key" in b}
    for m in re.finditer(r"having:\s*\[\{metric:\s*([a-z_0-9]+)", src):
        check(m.group(1) not in dedup_metrics,
              f"[dedup] {path.name}: metric '{m.group(1)}' declares dedup_key "
              f"but is used with HAVING — the planner rejects that combination")

check(has(SKILL, "projected dimension"),
      "[contract] SKILL.md lost the rule that every sort field must be the "
      "metric or a projected dimension (ORDER BY uses output aliases)")

# ---------------------------------------------------------------------------
# 2c. THE BQS CONTRACT (from models.py) must be stated where the agent reads it.
#     Each of these is a silent-wrong-answer path, not a rejection.
# ---------------------------------------------------------------------------
for label, phrase in [
    ("source is always set", "ALWAYS set it"),
    # Accuracy: omitting `source` with four registered sources RAISES
    # `Missing 'source'` — it does NOT silently answer from the wrong object.
    # An overstated warning is a correctness problem in its own right.
    ("why omitting source costs a hop", "only defaults when exactly ONE source"),
    ("exactly one metric per request", "ONE per request"),
    ("filters are ANDed, no OR", "there is no OR"),
    ("the operator whitelist", "is_null is_not_null"),
    ("negation goes through computed_filters", "negate"),
    ("time_grain for trend asks", "time_grain"),
]:
    check(has(SKILL, phrase),
          f"[contract] SKILL.md §0b lost {label} ('{phrase}')")
for label, phrase in [
    ("source is always set", "ALWAYS set `source`"),
    ("exactly one metric per request", "ONE `metric` per request"),
    ("filters are ANDed", "there is no"),
    ("no not_like", "NO not_like"),
    ("time_grain for trend asks", "time_grain"),
]:
    check(has(AGENTS, phrase),
          f"[contract] agents.yaml lost {label} ('{phrase}')")

# SCOPED DISCOVERY — discover_business_terms(source=...) exists. Fetching all
# four catalogs on every turn is 4x the context for one answer, and the routing
# table needed to choose is already in the instruction and the skill.
for path in [AGENTS, SKILL, TOOLS]:
    check(has(path, 'discover_business_terms(source'),
          f"[discovery] {path.name}: lost the scoped-discovery call — "
          f"discover_business_terms takes a `source` argument")
check(not re.search(r"discover_business_terms.{0,40}\(no arguments\)",
                    text(AGENTS), re.I | re.S),
      "[discovery] agents.yaml: back to calling discovery with no arguments — "
      "that returns ALL FOUR catalogs every turn")

# The B&D recipe must match the server's own docstring: bill_and_deliver is
# TOKEN-LESS; "Citi non-B&D" = syndicate_member 'citi' + bill_and_deliver negate.
# The non-B&D recipe must use filters that EXIST. Both wrong turns are
# specifically dangerous: negating participation returned a structural zero in
# production, and bnd_bank ne/not_in silently drops the no-B&D-recorded rows
# that a non-B&D answer is partly about.
for path in [TRANCHE, SKILL, AGENTS]:
    recipe = re.search(r"[Nn][Oo][Nn][- ]?B&D.{0,700}", text(path), re.S)
    window = " ".join(re.sub(r"[`*]", "", recipe.group(0)).split()) if recipe else ""
    check("syndicate_member_name" in window,
          f"[bnd] {path.name}: the non-B&D recipe no longer filters "
          f"participation via syndicate_member_name")
    # Must PROJECT it, not merely mention it — the split is made from the rows.
    check(re.search(r"project(ing)? bnd_bank", window, re.I) is not None,
          f"[bnd] {path.name}: the non-B&D recipe no longer PROJECTS bnd_bank — "
          f"without it the billed/not-billed split cannot be made")
    # The warnings must PROHIBIT, not merely name the wrong approach.
    check(re.search(r"(do not|don't|never|no)[^.]{0,40}bnd_bank ne\s*/\s*not_in",
                    window, re.I) is not None,
          f"[bnd] {path.name}: lost the PROHIBITION on bnd_bank ne/not_in, "
          f"which drops tranches with no B&D recorded")
    check(re.search(r"(do not|don't|never)\s+negate\s+participation", window, re.I)
          is not None,
          f"[bnd] {path.name}: lost the PROHIBITION on negating participation — "
          f"that was the production zero-result bug")
check(not re.search(r"bill_and_deliver[,(\s]+token", text(TRANCHE) + text(SKILL) + text(AGENTS)),
      "[bnd] a file passes a token to bill_and_deliver — it is token-less")

# Entitlement error codes reach the agent; the skill must handle them.
for code in ["entitlement_denied", "product_not_entitled"]:
    check(has(SKILL, code),
          f"[entitlement] SKILL.md does not handle the '{code}' error code")

# ---------------------------------------------------------------------------
# 3. THE %US% TRAP — matches RUSSIA and AUSTRIA
# ---------------------------------------------------------------------------
for path in OBJECTS + [SKILL]:
    for m in re.finditer(r"'%US%'|\"%US%\"|value:\s*\"%US%\"", text(path)):
        # Window, not line: YAML folding and markdown wrapping split the
        # warning across lines ("(matching\n  Russia)").
        raw = text(path)[max(0, m.start() - 160): m.end() + 160]
        window = " ".join(re.sub(r"[`*]", "", raw).split())
        # Legal only inside a warning that rules it out.
        check(
            re.search(r"\bnever\b|\bnot\b|russia|austria", window, re.I) is not None,
            f"[region] {path.name}: bare '%US%' used as a match pattern",
            "It matches RUSSIA and AUSTRIA. Use in ['United States','US'].",
        )
check(has(ORDER, "RUSSIA"), "[region] order object lost the %US% warning")
check(has(SKILL, "RUSSIA"), "[region] SKILL lost the %US% warning")

# ---------------------------------------------------------------------------
# 4. STORED-VALUE TRAPS — each one produced a wrong or empty answer in prod
# ---------------------------------------------------------------------------
TRAPS = [
    ("1x1 meeting literal", ORDER, "1x1"),
    ("1x1 excludes No Meeting", ORDER, "No Meeting"),
    ("M & A spacing", DEAL, "M & A"),
    ("refi split across two values", DEAL, "Debt Repayment"),
    ("Oil & Gas is not Energy", DEAL, "Oil & Gas"),
    ("deal_status case variants", DEAL, "'Open' vs 'OPEN'"),
    ("tenor format", TRANCHE, "10-YEAR"),
    ("coupon spacing", TRANCHE, "Fixed to FRN"),
    ("reg category literal", TRANCHE, "SEC Registered(Public)"),
    ("exchange full venue names", TRANCHE, "NEW YORK"),
    ("identifier casing per product", TRANCHE, "lowercase"),
    ("common stock label variants", TRANCHE, "%COMMON%"),
]
for label, path, phrase in TRAPS:
    check(has(path, phrase), f"[trap] {path.name}: lost '{phrase}' ({label})")

# The skill's trap table must carry them all — it is the layer that survives a
# catalog the model skimmed.
for phrase in ["1x1", "M & A", "Oil & Gas", "10-YEAR", "SEC Registered(Public)",
               "Fixed to FRN", "NEW YORK", "RUSSIA", "Debt Repayment"]:
    check(has(SKILL, phrase), f"[trap] SKILL.md: trap table lost '{phrase}'")

# ---------------------------------------------------------------------------
# 5. TIME WINDOWS — both bounds, and the upper bound is tomorrow-midnight
# ---------------------------------------------------------------------------
for path in OBJECTS[:3] + [SKILL]:
    check(has(path, "tomorrow-midnight"),
          f"[time] {path.name}: lost the tomorrow-midnight upper bound rule")
for path in OBJECTS + [SKILL]:
    check(not re.search(r"upper bound at today", text(path), re.I),
          f"[time] {path.name}: 'upper bound at today' is back — it drops "
          f"everything priced today")

# ---------------------------------------------------------------------------
# 6. TAXONOMY SUBSTITUTION — category is not classification
# ---------------------------------------------------------------------------
src = text(ORDER)
uns = src.find("unsupported_intents:")
before = src[:uns] if uns > 0 else src
for m in re.finditer(r"classification", before, re.I):
    line_start = before.rfind("\n", 0, m.start()) + 1
    line = before[line_start:before.find("\n", m.end())]
    check(
        re.search(r"untracked|different|not the", line, re.I) is not None,
        "[taxonomy] order object: 'classification' used as a synonym for "
        "investor_category outside unsupported_intents",
        "Their value sets do not overlap — substituting returns a WRONG "
        "population, not an approximate one.",
    )
check(has(ORDER, "investor_classification"),
      "[taxonomy] order object lost the investor_classification refusal")

# ---------------------------------------------------------------------------
# 7. NULL DISCLOSURE — a rule the ontology states must be executable
# ---------------------------------------------------------------------------
for path, field in [(ORDER, "investor_region"), (DEAL, "deal_region"),
                    (TRANCHE, "tranche_region")]:
    body = dict(blocks(path, "filters")).get(field, "")
    check("is_null" in body,
          f"[nulls] {path.name}: {field} has no is_null operator, so "
          f"'say how many null-region rows were excluded' cannot be executed")

# ---------------------------------------------------------------------------
# 8. B&D ATTRIBUTION — non-B&D is two predicates, roles are not attributable
# ---------------------------------------------------------------------------
check(has(TRANCHE, "bnd_bank"), "[bnd] tranche object lost the resolved bnd_bank")
check(has(TRANCHE, "not_like"), "[bnd] tranche object lost the not_like operator "
                                "needed for 'participated but did not bill'")
check(has(TRANCHE, "role_attribution"),
      "[bnd] tranche object lost the role_attribution refusal — matching the "
      "role list against the member list produces false attributions")
check(has(SKILL, "AND NOT") or has(SKILL, "not_like"),
      "[bnd] SKILL lost the two-predicate non-B&D recipe")

# ---------------------------------------------------------------------------
# 9. PIPE LISTS — position-aligned for matching, atomic for display
# ---------------------------------------------------------------------------
check(has(TRANCHE, "POSITION-ALIGNED"), "[pipe] tranche lost the alignment rule")
check(has(TRANCHE, "never split a pipe list across table columns"),
      "[pipe] tranche lost the display rule (the DEAL_ID-shows-an-ISIN bug)")
check(has(SKILL, "ATOMIC") and has(SKILL, "ISIN"),
      "[pipe] SKILL lost the pipe-list display rule")

# ---------------------------------------------------------------------------
# 10. ENTITY RESOLUTION — one hop, not exact-then-fallback
# ---------------------------------------------------------------------------
check(has(ENTITY, "ONE REQUEST, NOT TWO"),
      "[hops] entity object reverted to exact-first two-hop resolution")
check(not re.search(r"Try an?\s+exact.{0,40}first", text(ENTITY), re.I | re.S),
      "[hops] entity object: 'try exact first' is back — it misses by "
      "construction on partial names, so the fallback becomes the common path")
check(has(SKILL, "ONE request") or has(SKILL, "ONE REQUEST"),
      "[hops] SKILL lost the one-request resolution rule")

# ---------------------------------------------------------------------------
# 11. SURVIVAL KIT — the tool description ships on every request
# ---------------------------------------------------------------------------
for phrase in ["grain", "product", "SHARE COUNTS", "TEXT"]:
    check(has(TOOLS, phrase),
          f"[survival] tools.yaml: tool description lost '{phrase}' — this "
          f"description is the only layer that ships with every request")
live = "\n".join(l for l in text(TOOLS).splitlines() if not l.lstrip().startswith("#"))
check("mcp_tool_names: []" not in live,
      "[survival] tools.yaml: mcp_tool_names back to auto-discover; pin the "
      "read-only surface")

# The local `adk` runtime reads its ONLY toolset from this file — higher envs
# use the onboarding registry and never read it. So an empty list is not
# "defer to the registry", it is "no MCP tools locally", and the agent dies with
# Tool 'discover_business_terms' not found.
check(not re.search(r"^tools:\s*\[\s*\]\s*$", live, re.M),
      "[survival] tools.yaml has `tools: []` — the local runtime then has NO "
      "MCP toolset and every run fails with Tool 'discover_business_terms' not "
      "found. This file is local-only; it cannot shadow the registry.")
defined_tools = set(re.findall(r"^\s*-\s*name:\s*([A-Za-z0-9_\-]+)", live, re.M))
check(bool(defined_tools),
      "[survival] tools.yaml defines no tool at all")
for src_path, label in ((AGENTS, "agents.yaml"), (SKILLS, "skills.yaml")):
    body = "\n".join(l for l in text(src_path).splitlines()
                     if not l.lstrip().startswith("#"))
    for ref in set(re.findall(r"^\s*-\s*(?:name:\s*)?(capital_markets_oracle_mcp|text_to_sql_mcp)\s*$",
                              body, re.M)):
        check(ref in defined_tools,
              f"[survival] {label} references toolset '{ref}' but tools.yaml "
              f"defines {sorted(defined_tools) or 'nothing'} — local runs will "
              f"fail with Tool 'discover_business_terms' not found")
    check("text_to_sql_mcp" not in body,
          f"[survival] {label} still names the old toolset 'text_to_sql_mcp'; "
          f"the registry entry is 'capital_markets_oracle_mcp'")
check("mcp_server_url" in live,
      "[survival] tools.yaml lost mcp_server_url — the local runtime has no "
      "server to connect to")

# ---------------------------------------------------------------------------
# 12. SELF-CONTAINMENT — SKILL.md and skills.yaml must agree
# ---------------------------------------------------------------------------
check(has(SKILL, "self-contained"), "[skills] SKILL.md dropped the self-contained claim")
check(has(SKILLS, "SELF-CONTAINED"), "[skills] skills.yaml dropped the self-contained claim")
check(not has(SKILLS, "Load it alongside"),
      "[skills] skills.yaml is back to claiming a dependency SKILL.md denies")

# ---------------------------------------------------------------------------
# 13. HOUSE RULES that were each a separate v1 fix
# ---------------------------------------------------------------------------
for label, phrase in [
    ("count honesty", "showing N of M"),
    ("found-count over top-N", "I found 5 deals"),
    ("incomplete-data bullet", "Incomplete Data:"),
    ("grain-safe follow-up", "+N more"),
    ("never end with no text", "Never end a turn with no text"),
    ("ids are drill-down handles", "drill-down handles"),
    ("no SQL disclosure", "never disclose"),
]:
    check(has(SKILL, phrase), f"[house] SKILL.md lost the {label} rule ('{phrase}')")

# ---------------------------------------------------------------------------
# 14. AGENT INSTRUCTION — the survival kit. It loads on every turn even when a
#     skill does not, so it must carry every rule whose absence yields a WRONG
#     answer. v1 proved skill loading is discretionary.
# ---------------------------------------------------------------------------
for label, phrase in [
    ("skill-load does not end the turn", "does NOT end your turn"),
    ("discovery first", "discover_business_terms"),
    ("grain routing", "PICK THE OBJECT BY GRAIN"),
    # Pin the DOCTRINE, not a sentence — this pair false-alarmed once when rule 5
    # was reworded to carve out unit-free COUNT metrics. The doctrine is: a
    # product filter exists, and unit-bearing metrics are never totalled across
    # both products.
    ("product scoping", "`product` filter ('ECM' or 'DCM')"),
    ("units doctrine", "never total a SIZE/ALLOCATION/DEMAND metric across"),
    ("ids are text", "are TEXT"),
    ("no fabricated ids", "never substitute a"),
    ("unique tiebreaker", "UNIQUE KEY"),
    ("tomorrow-midnight", "TOMORROW-MIDNIGHT"),
    ("non-B&D is two predicates", "TWO predicates"),
    ("roles not attributable", "position-aligned"),
    ("%US% trap", "RUSSIA"),
    ("pipe cells atomic", "ONE cell"),
    ("count honesty", "FOUND count"),
    ("never end with no text", "Never end a turn with no text"),
]:
    check(has(AGENTS, phrase),
          f"[agent] agents.yaml: static_instruction lost the {label} rule "
          f"('{phrase}') — this layer loads even when the skill does not")

check(not has(AGENTS, "State which object (source), metric, dimensions"),
      "[agent] agents.yaml: the instruction is back to telling the agent to "
      "narrate source/metric/dimensions/filters — that leaks ontology internals "
      "and contradicts the skill's confidentiality rule")
check(has(AGENTS, "CONFIDENTIAL"),
      "[agent] agents.yaml: lost the confidentiality clause")
check(not has(AGENTS, "NOT YET RECEIVED"),
      "[agent] agents.yaml is still the placeholder")

# Referential integrity: every skill/tool the agent names must be defined.
for skill_name in re.findall(r"^\s+- ([a-z0-9-]+)\s*$",
                             text(AGENTS).split("skills:")[-1], re.M):
    check(f'"{skill_name}"' in text(SKILLS),
          f"[agent] agents.yaml references skill '{skill_name}', which "
          f"skills.yaml does not define")
# The toolset name must be IDENTICAL everywhere. The platform registry owns
# `capital_markets_oracle_mcp`; our config referred to `text_to_sql_mcp`, so the agent
# pointed at a toolset that does not exist there. Derive it, don't hardcode.
agent_tools = re.findall(r"^    tools:\n((?:      - \S+\n)+)", text(AGENTS), re.M)
tool_names = re.findall(r"- (\S+)", agent_tools[0]) if agent_tools else []
check(len(tool_names) == 1,
      f"[toolset] agents.yaml should attach exactly one MCP toolset, found "
      f"{tool_names}")
if tool_names:
    tname = tool_names[0]
    # EVERY toolset reference in skills.yaml must be that same name — one
    # stale entry is enough to hand a skill a tool the agent cannot resolve.
    skill_refs = re.findall(r"^      - name:\s*(\S+)\s*$", text(SKILLS), re.M)
    check(skill_refs and all(r == tname for r in skill_refs),
          f"[toolset] skills.yaml references {sorted(set(skill_refs))} but "
          f"agents.yaml attaches '{tname}' — a mismatch means tool-not-found")
    check(tname in text(SKILL),
          f"[toolset] SKILL.md does not use the toolset name '{tname}' that "
          f"agents.yaml attaches")
    # tools.yaml MUST define it. This file is read only by the local `adk`
    # runtime — higher environments use the onboarding registry and never load
    # it — so it cannot shadow anything, and leaving it out means local has no
    # MCP toolset at all. (A previous revision asserted the opposite and shipped
    # `tools: []`, which is what broke the local run.)
    defines = re.search(rf"^\s*-\s*name:\s*{re.escape(tname)}\s*(?:#.*)?$",
                        text(TOOLS), re.M) is not None
    check(defines,
          f"[toolset] tools.yaml does not define '{tname}' — the local runtime "
          f"reads its only toolset from this file, so the agent will fail with "
          f"Tool 'discover_business_terms' not found")

# ---------------------------------------------------------------------------
# 15. NO UNAPPLIED REVIEW MARKERS left in the shipped files
# ---------------------------------------------------------------------------
for path in OBJECTS + [SKILL, TOOLS, SKILLS, AGENTS]:
    leftover = re.findall(r"REVIEW [A-F]\d", text(path))
    check(not leftover,
          f"[hygiene] {path.name}: unapplied review markers {sorted(set(leftover))}")

# ---------------------------------------------------------------------------
# 16. THE PYTHON LAYER — we own this code now. These files are transcriptions
#     of the POC server with our fixes applied; the checks below stop a fix
#     from being lost in a re-transcription or a copy-back.
# ---------------------------------------------------------------------------
MCPSERVER = ROOT / "app" / "mcpserver.py"
PLANNER = ROOT / "app" / "bqs" / "planner.py"
MODELS = ROOT / "app" / "bqs" / "models.py"
BUILDER = ROOT / "app" / "bqs" / "sql_builder.py"
SCOPE_TEST = ROOT / "tests" / "test_entitlement_scope.py"
SOEID_MW = ROOT / "app" / "middleware" / "soeid_middleware.py"
SOEID_TEST = ROOT / "tests" / "test_soeid_resolution.py"
SECRETS = ROOT / "app" / "utils" / "cyberark_integration" / "secrets.py"
SECRETS_TEST = ROOT / "tests" / "test_cyberark_cache.py"
SUGGESTIONS = ROOT / "app" / "bqs" / "suggestions.py"
DISAMBIG_TEST = ROOT / "tests" / "test_disambiguation_scope.py"

for p in [MCPSERVER, PLANNER, MODELS, BUILDER, SCOPE_TEST, SOEID_MW, SOEID_TEST,
          SECRETS, SECRETS_TEST, SUGGESTIONS, DISAMBIG_TEST]:
    check(p.exists(), f"[python] {p.relative_to(ROOT)} is missing")

if SUGGESTIONS.exists():
    src = text(SUGGESTIONS)
    # The disambiguation probe must reuse the MAIN query's WHERE. Scoped by the
    # entity predicate alone it scans the whole view for all time and both
    # products: measured execute=6.11s vs enrich=34.89s on a single Blackrock
    # ask — 85% of a 41s call — and it offered entities with no rows in the
    # answer at all.
    check("_build_where" in src,
          "[latency] suggestions.py: the disambiguation probe no longer reuses "
          "sql_builder._build_where — it will drop the date range and product "
          "and rescan the entire view (measured enrich=34.89s vs execute=6.11s)")
    # Assert the CALL SITE. The unit test exercises the helper directly, so it
    # stays green even if the caller quietly stops passing the plan — which is
    # exactly the regression that reinstates the 35s unscoped probe.
    # A name is not unique. Offering the user a list of bare NAMES to retype is
    # both ambiguous and unusable — the Blackrock answer listed 10 names with no
    # GP ids because the server only ever sent names.
    check("entity_id_column" in src,
          "[answer] suggestions.py: the probe no longer returns the paired id, "
          "so disambiguation can only offer names the user must retype")
    check('AS "entity_id"' in src,
          "[answer] suggestions.py: the entity_id column is no longer selected")
    for ont, filt, idcol in (
        (ORDER, "investor_name", "investor_gp_id"),
        (ORDER, "deal_name", "deal_id"),
        (DEAL, "deal_name", "deal_id"),
        (DEAL, "issuer_name", "gfcid"),
        (TRANCHE, "deal_name", "deal_id"),
        (TRANCHE, "issuer_name", "gfcid"),
        (ENTITY, "entity_name", "entity_id"),
    ):
        body = text(ont)
        m = re.search(rf"^  {filt}:\n(?:    .*\n)*?    entity_id_column: {idcol}\s*$",
                      body, re.M)
        check(m is not None,
              f"[answer] {ont.name}: filter '{filt}' lost "
              f"'entity_id_column: {idcol}' — its disambiguation list will carry "
              f"names with no id")

    check("_build_entity_distinct_probe(spec, ef, dialect, plan)" in src,
          "[latency] suggestions.py: build_disambiguation no longer passes the "
          "plan to the probe — it falls back to the unscoped shape and rescans "
          "the whole view (measured enrich=34.89s vs execute=6.11s)")

_SVC = ROOT / "app" / "services" / "domain_query_service.py"
if _SVC.exists():
    check("self._enrich_result(result, req, spec, dialect, len(rows), plan)" in text(_SVC),
          "[latency] domain_query_service.py: the plan is no longer handed to "
          "_enrich_result, so the disambiguation probe cannot be scoped")

if SECRETS.exists():
    src = text(SECRETS)
    # Every CyberArk resolve spawns a bash script that boots a ~2 GB JVM
    # SecretAgent — measured 5.5s and 7.7s on two consecutive queries, paid
    # inside the executor's execute= phase on EVERY query.
    check("_SECRET_CACHE" in src and "_cached_secret(" in src,
          "[latency] secrets.py: the per-FID secret cache is gone — every query "
          "boots a fresh SecretAgent JVM (5-8s) to fetch a credential that never "
          "changed")
    # Assert the CALL SITE, not the definition — leaving `def _fid_lock` behind
    # while dropping `with _fid_lock(...)` would satisfy a bare name check and
    # silently restore the stampede.
    check("with _fid_lock(" in src,
          "[latency] secrets.py: the per-FID lock is no longer taken around the "
          "fetch — N concurrent cold callers will each boot their own JVM")
    check("invalidate_secret_cache" in src,
          "[security] secrets.py: invalidate_secret_cache is gone — a rotated "
          "credential would then stay stale for the whole TTL with no way out")
    check("if secret and ttl:" in src,
          "[security] secrets.py: the cache no longer guards on a truthy secret "
          "— a FAILED lookup must never be cached, or one transient failure is "
          "pinned for the entire TTL")
    check("CYBERARK_CACHE_TTL_SECONDS" in src,
          "[latency] secrets.py: the TTL is no longer configurable/disableable")

if SOEID_MW.exists():
    src = text(SOEID_MW)
    # QA sent no identity header at all; the nl2sql channel passes ?user_id=.
    check("request.query_params.get(" in src,
          "[python] soeid_middleware.py: query-param identity resolution is gone "
          "— a caller reaching /mcp?user_id=<soeid> resolves to an empty SOEID "
          "and the entitlement gate denies with missing_soeid")
    check("CANDIDATE_ID_QUERY_PARAMS" in src,
          "[python] soeid_middleware.py: CANDIDATE_ID_QUERY_PARAMS is gone")
    # Headers stay the trusted channel; the query param is only the fallback.
    check(src.index("CANDIDATE_ID_HEADERS:") < src.index("CANDIDATE_ID_QUERY_PARAMS:"),
          "[python] soeid_middleware.py: query params are now checked BEFORE "
          "headers — a caller could override the gateway-set identity header")
    for alias in ("x-user-id", "x-citiportal-loginid", "x-citi-soeid", "x-soeid",
                  "x-authenticated-userid", "x-forwarded-user", "x-remote-user"):
        check(f'"{alias}"' in src,
              f"[python] soeid_middleware.py: lost header alias {alias}")

# LATENCY: measured 2026-08-07 — one ask = 59s, of which run_bqs_query was 36s.
# build_disambiguation costs a SECOND serial DB round-trip whenever an
# entity-name filter's field was not projected as a dimension; projecting it is
# free. Both config layers must carry that, and the server must keep the phase
# timings that let anyone re-measure.
SERVICE = ROOT / "app" / "services" / "domain_query_service.py"
if SERVICE.exists():
    svc = text(SERVICE)
    check("BQS timing source=" in svc,
          "[latency] domain_query_service.py: the phase-timing log is gone — "
          "build/execute/format/enrich is the only way to tell whether a slow "
          "hop is Trino or us")
    for phase in ("t_build", "t_exec", "t_format", "t_enrich"):
        check(phase in svc,
              f"[latency] domain_query_service.py: timer {phase} is gone")
for path, label in ((SKILL, "SKILL.md"), (AGENTS, "agents.yaml")):
    check(re.search(r"(?i)(project|dimensions).{0,400}(round.?trip|second database)",
                    text(path), re.S),
          f"[latency] {label}: lost the rule that a FILTERED name field must "
          f"also be projected in dimensions — without it every named-entity "
          f"query pays an extra serial DB probe in build_disambiguation")

# COUNT metrics are unit-free — one request grouped by product, not one per
# product. Measured 2026-08-07: the agent split a currency_count ask into an ECM
# request (9.9s) and a DCM request (27.1s); one grouped request would have done.
# ROW CAP — the largest single latency item measured. Event 10 of the 2026-08-09
# trace: candidatesTokenCount 9,299 / thoughtsTokenCount 266, i.e. 67s of a 153s
# answer was the model typing 189 table rows, and 98.7% of the session's output
# tokens were that one table. Nothing capped it before.
for path, label in ((SKILL, "SKILL.md"), (AGENTS, "agents.yaml")):
    check(re.search(r"(?i)never print more than 50 data rows", text(path)),
          f"[latency] {label}: lost the 50-row display cap — an unbounded table "
          f"is the biggest single cost in an answer (measured 9,299 output "
          f"tokens / 67s for 189 rows)")
    check(re.search(r"(?i)showing 50 of", text(path)),
          f"[latency] {label}: lost the 'showing 20 of N' caption, which is what "
          f"keeps the capped table an HONEST answer to 'list all'")
    check(re.search(r"(?i)(wide|8\\+ columns)", text(path)),
          f"[latency] {label}: lost the wide-table clause — 50 rows of an "
          f"8+ column table with pipe-list cells costs about twice 50 narrow "
          f"ones, and the budget is tokens, not rows")

# PRESENTATION CONTRACT (user, 2026-08-09): a banker picks by NUMBER, and an
# entity is only actionable with its id. The Blackrock answer listed 10 entity
# names as BULLETS with no GP ids, so the only way to drill in was to retype a
# name — and names are not unique.
for path, label in ((SKILL, "SKILL.md"), (AGENTS, "agents.yaml")):
    body = text(path)
    check(re.search(r"(?i)(choose|CHOOSE) from is NUMBERED", body),
          f"[answer] {label}: lost the rule that CHOICE lists are numbered, not "
          f"bulleted — the user has to retype an entity name to pick one")
    check(re.search(r"(?i)reply with a number", body),
          f"[answer] {label}: lost the 'reply with a number' invitation")
    # Anchor on the RULE, not the token: "gpnum" already appears in the routing
    # table, so a bare token check passes even with the rule deleted.
    check(re.search(r"(?i)never shown by name alone", body),
          f"[answer] {label}: lost the rule that an entity is never shown by "
          f"name alone — a name is not a drill-down handle and is not unique; "
          f"the GP id (GPNUM) / GFCID / DEAL_ID must sit beside it")
    check(re.search(r"(?i)51.{0,6}100", body),
          f"[answer] {label}: lost the continue-the-numbering-across-pages rule "
          f"(1-50 then 51-100), so page 2 restarts at 1 and rows look duplicated")
    # "List all the multi-currency deals" printed all 189 rows (9,828 tokens,
    # 63s) because the cap said "print more only if the user explicitly asks" —
    # and the model read the word "all" in the QUESTION as that request.
    check(re.search(r'(?i)"?list all"? is not a request for more rows', body),
          f"[latency] {label}: lost the carve-out that \"list all\"/\"show all\" "
          f"describes the scope of the QUESTION, not the size of the table — "
          f"without it the cap is silently lifted by the word 'all'")
    # Ported from v1 skill-v7 §14 after a side-by-side diff (2026-08-09).
    for phrase, why in (
        (r"never a bare count",
         "a listing ask answered with a number is a wrong answer"),
        (r"(?i)export is not available",
         "the user asks to download and gets no honest answer (export is out of MVP)"),
        (r"(?i)answerable",
         "an ECM-only user gets offered DCM follow-ups that cannot run"),
        (r"(?i)book profile",
         "order-level asks return a truncated dump instead of a book profile"),
        (r"(?i)escalated",
         "the agent invents an escalation path that does not exist"),
    ):
        check(re.search(phrase, body),
              f"[answer] {label}: lost a v1 presentation rule — {why}")
    check(re.search(r"(?i)aggregate\W{0,4}instead", body),
          f"[answer] {label}: lost the three-doors offer (filter / aggregate / "
          f"next page) — paging alone makes the user walk the whole list")
    check(re.search(r"(?i)ask for the next 50", body),
          f"[answer] {label}: lost the explicit 'ask for the next 50' offer, so a "
          f"capped listing looks like the whole answer")

for path, label in ((SKILL, "SKILL.md"), (AGENTS, "agents.yaml")):
    body = text(path)
    check(re.search(r"(?i)count.{0,120}unit.?free", body, re.S),
          f"[latency] {label}: lost the rule that COUNT metrics are unit-free "
          f"and take ONE request grouped by product, not one request per product")

if MCPSERVER.exists():
    src = text(MCPSERVER)
    # IDENTITY IS THE CALLER'S. A server-side SOEID fallback attributes one
    # person's queries AND entitlements to every unidentified caller, and makes
    # a broken identity chain look like a correct answer — a local default of
    # sr37832 was scoping real results as late as 2026-08-09.
    check('os.getenv("LOCAL_DEFAULT_SOEID"' not in src,
          "[security] mcpserver.py: the LOCAL_DEFAULT_SOEID fallback is back — "
          "an unidentified caller silently runs as somebody else")
    check('os.getenv("MCP_CALLER_SOEID"' not in src,
          "[security] mcpserver.py: the MCP_CALLER_SOEID env fallback is back — "
          "identity must come from the request, not the environment")
    check("def _require_caller_soeid" in src,
          "[security] mcpserver.py: _require_caller_soeid is gone — a request "
          "with no caller identity would be served")
    check("denial = _require_caller_soeid()" in src,
          "[security] mcpserver.py: run_bqs_query no longer calls "
          "_require_caller_soeid, so the guard is dead code")
    check('"code": "missing_soeid"' in src,
          "[security] mcpserver.py: the missing_soeid refusal is gone")
    if "denial = _require_caller_soeid()" in src and "denial = _entitlement_gate" in src:
        check(src.index("denial = _require_caller_soeid()")
              < src.index("denial = _entitlement_gate"),
              "[security] mcpserver.py: the identity check now runs AFTER the "
              "entitlement gate — it must run first, so it still applies when "
              "ECM_DCM_ENTITLEMENT_FEATURE_FLAG is off")
    # Transport parity with the v1 nl2sql server, which builds its app as
    # mcp.http_app(middleware=[...]) with no stateless flag. Stateless mode
    # drops GET /mcp with a bare 405 before the MCP layer sees it, so a client
    # that opens its session over SSE never gets a tool list.
    src_code = "\n".join(l for l in src.splitlines()
                         if not l.lstrip().startswith("#"))
    # Session mode must stay a SWITCH, not a hardcoded choice. Both modes have a
    # real failure: stateless 405s a GET/SSE client; stateful 404s every POST
    # whose session the pod has not seen (measured in QA 2026-08-09 across
    # replicas). The default is stateless because this service is horizontally
    # scaled and the ADK client only ever POSTs.
    check("MCP_STATELESS_HTTP" in src_code,
          "[python] mcpserver.py: the session mode is hardcoded again — keep "
          "MCP_STATELESS_HTTP so it can be flipped without a rebuild")
    check('os.getenv("MCP_STATELESS_HTTP", "true")' in src_code,
          "[python] mcpserver.py: MCP_STATELESS_HTTP no longer defaults to true "
          "— stateful across >1 replica returns 404 on every POST whose session "
          "landed on another pod")
    check("stateless_http=stateless" in src_code,
          "[python] mcpserver.py: http_app() is no longer given the resolved "
          "session mode")
    check("mcp.http_app(" in src,
          "[python] mcpserver.py: the HTTP app is no longer built via "
          "mcp.http_app()")
    # The fix: intersect requested with entitled.
    check("scope = [p for p in requested if p in entitled] or entitled" in src,
          "[python] mcpserver.py: the entitlement intersect (FIX 1) is gone — a "
          "dual-entitled caller asking for ECM would silently get ECM+DCM, and "
          "size/allocation metrics would sum shares with money")
    check('"value": scope[0]' in src and '"value": scope' in src,
          "[python] mcpserver.py: the injected product filter no longer uses "
          "`scope` — it is back to injecting the full entitlement")
    check('"value": entitled[0]' not in src,
          "[python] mcpserver.py: the OLD full-entitlement injection is back")
    # The three fail-open paths must stay visibly flagged until decided.
    # Was 3. The RUN_MODE one is DECIDED and gone: the entitlement gate no
    # longer consults the run mode at all. Two remain, both on import/response
    # failure paths.
    check(src.count("FAIL-OPEN (undecided)") == 2,
          f"[python] mcpserver.py: expected 2 FAIL-OPEN markers, found "
          f"{src.count('FAIL-OPEN (undecided)')} — the entitlement fail-open "
          f"paths must stay visible until they are decided")
    check("PREFER passing one name" in src,
          "[python] mcpserver.py: discover_business_terms docstring no longer "
          "steers the agent to a single source")

if MODELS.exists():
    ops = re.search(r"class FilterOperator.*?(?=\nclass )", text(MODELS), re.S)
    check(ops is not None and "not_like" not in ops.group(0).lower().replace("no not_like", ""),
          "[python] models.py: a not_like operator appeared in FilterOperator — "
          "if that is intentional, the ontologies and skill must be updated too")

SERVICE = ROOT / "app" / "services" / "domain_query_service.py"
check(SERVICE.exists(), "[python] app/services/domain_query_service.py is missing")
if SERVICE.exists():
    src = text(SERVICE)
    check("DEPLOYMENT LANDMINE" in src,
          "[python] domain_query_service.py: lost the BQS_ENABLED_SOURCES "
          "landmine note — an allow-list still naming 'capital_markets' silently "
          "disables all four renamed objects")
    check("authoritative statement of the suggestion" in src,
          "[python] domain_query_service.py: lost the note that suggestions "
          "fire ONLY on 0 rows and disambiguation ONLY on non-zero")
    check("`sql_audit` puts" in src,
          "[python] domain_query_service.py: lost the note that sql_audit puts "
          "the generated SQL in the agent-visible payload")
# The skill must know the SQL is in the payload, not merely conceptual.
check(has(SKILL, "generated_sql"),
      "[contract] SKILL.md no longer names `generated_sql` — that is the "
      "RESPONSE key (sql_audit is only formatter's parameter name), and the SQL "
      "is in the payload the agent receives")
# STALE ASSERTION FIXED (2026-08-10). This used to require SKILL.md to say
# "Truncation is not reported ... no flag, no limit echo". That predates paging:
# formatter.format_result sets `truncated`/`next_offset`/`paging` whenever
# `row_count >= limit` (including the 50-row default) or the response cap clipped
# the rows — which is exactly what the formatter check below (`next_offset` and
# `truncated` in src) requires. The two checks contradicted each other, and the
# skill was teaching the agent to ignore a flag the server does send.
check(has(SKILL, "Truncation IS flagged"),
      "[contract] SKILL.md lost the truncation rule — the server DOES send "
      "`truncated`/`next_offset`/`paging` when row_count reaches the limit in "
      "force or the response cap clipped; the agent must read that as 'more "
      "rows exist' and page with offset, not re-run with a bigger limit")

SUGGESTIONS = ROOT / "app" / "bqs" / "suggestions.py"
check(SUGGESTIONS.exists(), "[python] app/bqs/suggestions.py is missing")
if SUGGESTIONS.exists():
    src = text(SUGGESTIONS)
    check("PERFORMANCE: this probe is UNSCOPED" in src,
          "[python] suggestions.py: lost the note that the 0-row DISTINCT probe "
          "carries no product/date filter — a bad guess is the SLOW path")
    check("makes\n            #    disambiguation cost nothing" in src
          or "disambiguation cost nothing" in src,
          "[python] suggestions.py: lost the note that projecting the filtered "
          "name field makes disambiguation free")
# Both facts must reach the agent, not just the server code.
check(has(SKILL, "the *slow* path"),  # short phrase: the full sentence wraps
      "[perf] SKILL.md lost the rule that a 0-row query costs an extra "
      "unscoped DISTINCT scan per suggestable filter")
check(has(SKILL, "Always PROJECT the name field you filter on"),
      "[perf] SKILL.md lost the rule that projecting the filtered name field "
      "makes disambiguation free")

ONTOLOGY = ROOT / "app" / "bqs" / "ontology.py"
check(ONTOLOGY.exists(), "[python] app/bqs/ontology.py is missing")

if ONTOLOGY.exists():
    src = text(ONTOLOGY)
    # `values:` is a suggestion-ranking list, NOT validation. A partial list
    # REPLACES the live DISTINCT probe and makes did_you_mean worse — so only
    # declare it for enums we know completely.
    check("instead of a live DISTINCT probe" in src,
          "[python] ontology.py: lost the note that `values` replaces the live "
          "DISTINCT probe — that is why partial value lists are harmful")
    # Hot reload is a behaviour, not a comment: get() calls reload() every time,
    # so a YAML change goes live without a redeploy — which is exactly why
    # ontology_check.py must run before every copy.
    getdef = re.search(r"def get\(self.*?(?=\n    def )", src, re.S)
    check(getdef is not None and "self.reload()" in getdef.group(0),
          "[python] ontology.py: get() no longer reloads — ontology YAML changes "
          "would stop taking effect without a redeploy, which changes how we ship")

# Only enums we know completely may declare `values:`. Anything else degrades
# suggestions by replacing real DISTINCTs with our guess.
KNOWN_COMPLETE_ENUMS = {"product", "entity_type", "deal_sharing_type"}
for path in OBJECTS:
    for name, body in blocks(path, "filters"):
        if "values:" in body:
            check(name in KNOWN_COMPLETE_ENUMS,
                  f"[values] {path.name}: filter '{name}' declares `values:` but "
                  f"is not a known-complete enum {sorted(KNOWN_COMPLETE_ENUMS)}",
                  "A partial list replaces the live DISTINCT probe, so "
                  "did_you_mean starts ranking against our guess instead of the "
                  "real values.")

# The skill must distinguish recoverable (0-row) traps from wrong-population
# ones — suggestions only fire on 0 rows.
check(has(SKILL, "Wrong-population traps"),
      "[trap] SKILL.md §7b lost the distinction between 0-row traps (the server "
      "suggests a fix) and wrong-population traps (nothing fires)")

if PLANNER.exists():
    src = text(PLANNER)
    check("PRESENT, not that it scopes to a\n    # single value" in src.replace("\r",""),
          "[python] planner.py: lost the note that requires_filters checks "
          "PRESENCE, not single-value scoping")
    check('code="missing_required_filter"' in src,
          "[python] planner.py: requires_filters enforcement is gone — the "
          "units guard in all four ontologies depends on it raising")

# The scope test is the executable proof of FIX 1; it must pass.
if SCOPE_TEST.exists():
    import subprocess
    rc = subprocess.run([sys.executable, str(SCOPE_TEST)],
                        capture_output=True, text=True).returncode
    check(rc == 0, "[python] entitlement_scope_test.py FAILED — run it directly "
                   "to see which case regressed")

if SOEID_TEST.exists():
    import subprocess
    rc = subprocess.run([sys.executable, str(SOEID_TEST)],
                        capture_output=True, text=True).returncode
    check(rc == 0, "[python] test_soeid_resolution.py FAILED — run it directly "
                   "to see which identity case regressed")

if SECRETS_TEST.exists():
    import subprocess
    rc = subprocess.run([sys.executable, str(SECRETS_TEST)],
                        capture_output=True, text=True).returncode
    check(rc == 0, "[python] test_cyberark_cache.py FAILED — run it directly to "
                   "see which cache guarantee regressed")

# A test that monkeypatches at IMPORT time poisons every test that runs after
# it in the same process. test_cyberark_cache.py did exactly that and made the
# repo's own tests/test_secrets.py fail with "'s3cr3t-value' != 'supersecret'".
if SECRETS_TEST.exists():
    tsrc = text(SECRETS_TEST)
    check("def teardown_function" in tsrc and "_ORIG_RUN_RETRIEVE" in tsrc,
          "[python] test_cyberark_cache.py: patches are no longer restored in a "
          "teardown — a global monkeypatch here leaks into every later test in "
          "the suite")
    # Nothing may be assigned onto the module at import time (column 0).
    import re as _re
    check(not _re.search(r"^sec\.\w+\s*=", tsrc, _re.M),
          "[python] test_cyberark_cache.py: something patches the secrets module "
          "at MODULE level — patch inside setup_function so it can be undone")

if DISAMBIG_TEST.exists():
    import subprocess
    rc = subprocess.run([sys.executable, str(DISAMBIG_TEST)],
                        capture_output=True, text=True).returncode
    check(rc == 0, "[python] test_disambiguation_scope.py FAILED — the probe is "
                   "no longer scoped like the query it explains")

# ---------------------------------------------------------------------------
# Entitlement service — it sits in front of EVERY query, so its cache is a
# latency guarantee and its failure taxonomy is a correctness one.
# ---------------------------------------------------------------------------
ENT_SVC = ROOT / "app" / "services" / "entitlement_service.py"
ENT_CACHE_TEST = ROOT / "tests" / "test_entitlement_cache.py"
AUTH_MW = ROOT / "app" / "middleware" / "auth_middleware.py"

for p in [ENT_SVC, ENT_CACHE_TEST, AUTH_MW]:
    check(p.exists(), f"[python] {p.relative_to(ROOT)} is missing")

if ENT_SVC.exists():
    src = text(ENT_SVC)

    check("_cache_get_fresh" in src and "_cache_put" in src,
          "[latency] entitlement_service.py: the per-SOEID cache is gone — the "
          "ECMO API is back to one live POST on every single query")
    check("ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS" in src,
          "[latency] entitlement_service.py: the cache TTL is no longer tunable")
    check("_cache_get_stale" in src and "cache_fallback" in src,
          "[resilience] entitlement_service.py: the last-known-good fallback is "
          "gone — one API blip now revokes every active session")
    check("ECM_DCM_ENTITLEMENT_STALE_MAX_AGE_SECONDS" in src,
          "[security] entitlement_service.py: the stale scope is no longer "
          "bounded — a revocation would never land during a long outage")

    # A misconfigured deployment must NEVER be served from stale cache: we
    # cannot verify a scope when we cannot reach the thing that grants it.
    if "except ValueError" in src:
        _vblock = src.split("except ValueError", 1)[1].split("except ", 1)[0]
        check("_cache_get_stale" not in _vblock,
              "[security] entitlement_service.py: the misconfiguration branch now "
              "serves a stale scope — it must fail closed, only transient "
              "failures may fall back")

    # `reason` is copied verbatim into the agent-facing error `code` by
    # mcpserver._entitlement_gate, so an interpolated one ships the upstream
    # response body to the model and out to the user.
    check('"reason": f"' not in src,
          "[security] entitlement_service.py: a `reason` is being interpolated — "
          "it becomes the agent-facing error code, so it must stay a stable slug "
          "and the detail must go to the log instead")

    # requests' exceptions are OSErrors, and JSONDecodeError is a ValueError.
    # Neither lands where you would expect, and run_bqs_query has no handler.
    check("requests.RequestException" in src,
          "[correctness] entitlement_service.py: a connection error or timeout is "
          "an OSError, not a RuntimeError — uncaught it escapes run_bqs_query, "
          "which has no exception handler, and reaches the agent as a crash")
    check("unparseable" in src,
          "[correctness] entitlement_service.py: response.json() is unguarded — "
          "requests' JSONDecodeError subclasses ValueError, so a proxy's HTML "
          "error page gets reported to the user as 'service misconfigured'")

    check("_build_session().post" not in src and "_get_session" in src,
          "[latency] entitlement_service.py: a Session is being built per call "
          "again, which discards the connection pool it just configured and pays "
          "a fresh TCP+TLS handshake on every query")
    check("with _soeid_lock(" in src,
          "[latency] entitlement_service.py: the per-SOEID lock is not held around "
          "the fetch — a cold burst makes N API calls instead of one")

    # This function decides what a person may see. Verified against QAT
    # 2026-08-09: the shapes below are what the API actually returns, and a
    # SOEID with no grant is correctly denied. Speculative branches (top-level
    # arrays, gateway envelopes) were added on a hypothesis, disproved, and
    # removed — every extra branch is another way to read a grant that was
    # never issued, because _extract_products_from_clause matches ECM/DCM
    # ANYWHERE in a string.
    _parse = src.split("def _parse_entitlement_response", 1)[-1].split("\ndef ", 1)[0]
    check("_parse_entitlement_response(" not in _parse,
          "[security] entitlement_service.py: the response parser recurses into "
          "nested envelopes — an unrecognised shape must DENY and log its shape, "
          "not go hunting for an ECM/DCM token somewhere inside it")
    check("Response shape:" in src,
          "[diagnostics] entitlement_service.py: an empty product list no longer "
          "logs the response SHAPE — nothing then distinguishes a real denial "
          "from a parser miss, which are fixed by different teams")

if ENT_CACHE_TEST.exists():
    import subprocess
    rc = subprocess.run([sys.executable, str(ENT_CACHE_TEST)],
                        capture_output=True, text=True).returncode
    check(rc == 0, "[python] test_entitlement_cache.py FAILED — run it directly "
                   "to see which entitlement guarantee regressed")

if MCPSERVER.exists():
    src = text(MCPSERVER)
    # Identity and entitlement fail in OPPOSITE directions (closed vs open).
    # Sharing one import block made a missing entitlement_service present itself
    # as a missing header on every request.
    check("_SOEID_AVAILABLE" in src,
          "[correctness] mcpserver.py: identity and entitlement share an import "
          "flag again — an entitlement_service import failure will masquerade as "
          "`missing_soeid` on every query")
    check("if not _SOEID_AVAILABLE:\n        return None" in src,
          "[correctness] mcpserver.py: _resolve_soeid no longer gates on "
          "_SOEID_AVAILABLE — it is reading the wrong subsystem's flag")
    check("identity_unavailable" in src,
          "[correctness] mcpserver.py: a startup identity failure reports as "
          "`missing_soeid`, which sends whoever debugs it after a header that "
          "was there all along")
    # The helm chart ships entitlementFeatureFlag "false" with an EMPTY
    # productEntitlementUrl / entitlementPolicyId. Flipping the flag alone makes
    # get_entitled_products raise on the empty URL, so every query is refused
    # with `entitlement_misconfigured` — a total outage from a one-word edit.
    check("_log_entitlement_config" in src,
          "[deployment] mcpserver.py: the startup entitlement-config check is "
          "gone — a values file that enables the gate without the URL and policy "
          "id would take the agent down on the first query with no warning at "
          "pod start")
    check("_log_entitlement_config()" in src.split("def _log_entitlement_config", 1)[-1],
          "[deployment] mcpserver.py: _log_entitlement_config is defined but "
          "never called — it only helps if it runs at startup")

    # The entitlement gate must behave IDENTICALLY in every environment. The old
    # `if _is_local_mode(): return False` keyed the gate off RUN_MODE, which
    # defaults to "local" — so the gate was off unless a deployment remembered
    # to set a variable, and a laptop could never reproduce an entitlement bug.
    check("def _is_local_mode" not in src,
          "[security] mcpserver.py: the local-mode bypass is back — RUN_MODE "
          "defaults to 'local', so this silently disables the entitlement gate "
          "in any environment that does not override it")
    # Inspect the EXECUTABLE body only — the docstring quotes the removed line
    # to explain why it went, and a substring check trips over its own comment.
    import ast as _ast
    _fn = next((n for n in _ast.walk(_ast.parse(src))
                if isinstance(n, _ast.FunctionDef)
                and n.name == "_ecm_entitlement_enabled"), None)
    _code = ""
    if _fn is not None:
        _stmts = [s for s in _fn.body
                  if not (isinstance(s, _ast.Expr)
                          and isinstance(getattr(s, "value", None), _ast.Constant)
                          and isinstance(s.value.value, str))]
        _code = "\n".join(_ast.get_source_segment(src, s) or "" for s in _stmts)
    check(_fn is not None and "_is_local_mode" not in _code and "RUN_MODE" not in _code,
          "[security] mcpserver.py: _ecm_entitlement_enabled consults the run "
          "mode again — ECM_DCM_ENTITLEMENT_FEATURE_FLAG must be the only switch")

    # Fail on the FIRST tool the agent calls, not the last. Gating only
    # run_bqs_query meant an unentitled caller burned transfer -> load_skill ->
    # discover -> build-a-request before hearing "no".
    _disc = src.split("def discover_business_terms", 1)[-1].split("\n    @", 1)[0]
    check("_entitlement_preflight()" in _disc,
          "[latency] mcpserver.py: discover_business_terms no longer runs the "
          "entitlement preflight — a refusal costs four LLM turns instead of one, "
          "and run_bqs_query's check loses its warm cache")
    check("_require_caller_soeid" in src.split("def _entitlement_preflight", 1)[-1]
          .split("\ndef ", 1)[0],
          "[security] mcpserver.py: _entitlement_preflight skips the identity "
          "check — discover would answer a caller with no SOEID")

if AUTH_MW.exists():
    src = text(AUTH_MW)
    check("DISABLE_COIN" in src and 'strip().lower()' in src,
          "[correctness] auth_middleware.py: DISABLE_COIN is compared raw again — "
          "`DISABLE_COIN=True` would not match and would silently switch "
          "authentication back on")
    check("COIN token validation is DISABLED" in src,
          "[security] auth_middleware.py: the startup warning is gone — an unset "
          "DISABLE_COIN means NO tool call is authenticated, and nothing in the "
          "logs would say so")

# ---------------------------------------------------------------------------
# Response size — rows go straight into an LLM context.
#
# An omitted `limit` used to resolve to spec.max_limit (5000). A listing that
# hit it ended the turn with RESOURCE_EXHAUSTED at ~300k tokens. Two bounds now
# exist and they are NOT interchangeable: the planner's default bounds what the
# warehouse does, the formatter's cap bounds what the model reads. Capping
# without `offset` would be worse than neither — rows past the cap would be
# unreachable, while the skill promises the user "ask for the next 50".
# ---------------------------------------------------------------------------
FORMATTER = ROOT / "app" / "bqs" / "formatter.py"
ONTOLOGY_PY = ROOT / "app" / "bqs" / "ontology.py"
PAGING_TEST = ROOT / "tests" / "test_response_paging.py"

for p in [FORMATTER, PAGING_TEST]:
    check(p.exists(), f"[python] {p.relative_to(ROOT)} is missing")

if PLANNER.exists():
    src = text(PLANNER)
    check("req.limit or spec.max_limit" not in src,
          "[context] planner.py: an omitted limit resolves to spec.max_limit "
          "again — that is 5000 rows into an LLM context and the "
          "RESOURCE_EXHAUSTED path at ~300k tokens")
    check("_default_row_limit()" in src,
          "[context] planner.py: the small default page is gone — an omitted "
          "limit must mean a page, not everything the object allows")
    check("offset" in src and "offset_without_order" in src,
          "[correctness] planner.py: offset lost its deterministic-sort "
          "guarantee — OFFSET without ORDER BY is sampling, not paging, and "
          "page 2 can repeat or skip rows from page 1")

# DATE ANCHOR (added 2026-08-11). A model does not know today's date and will
# anchor relative windows on its training cutoff. Measured: "past 12 month"
# became 2023-05-17..2024-05-18 against 2024-2026 data — 27 months stale, zero
# rows, on a correctly-routed question. V1 carried this rule in two places
# (agents-v6.yml DATE ANCHOR + ADD_MONTHS(SYSDATE,-12)); the V2 rewrite dropped
# both. The server now emits current_date/date_anchor in discovery, and the
# skill must tell the agent that value is the ONLY authority for "today".
check("current_date" in text(ONTOLOGY_PY) and "date_anchor" in text(ONTOLOGY_PY),
      "[time] ontology.py: discovery() no longer emits current_date/date_anchor "
      "— the agent has no way to know today's date and every relative window "
      "('last 12 months', 'YTD', 'recent') silently uses the model's training "
      "cutoff instead, returning zero rows against current data")
check(re.search(r"(?i)date anchor", text(SKILL)),
      "[time] SKILL.md: lost the DATE ANCHOR rule — without it the agent does "
      "not know that current_date from discovery is the only authority for "
      "'today', and will infer relative windows from its training cutoff")

# PER-PRODUCT APPLICABILITY (added 2026-08-11). 28 columns are HARD NULL on one
# product (CAST(NULL) in the view's other UNION branch). Prose said so for 23 of
# them and nothing enforced it, so an impossible combination returned an empty
# result the agent misread as "no data". This hid as an ENVIRONMENT bug: a
# single-product login gets `product eq X` injected by the entitlement gate and
# never trips it, while a dual-entitled login — which is what production has —
# fails on the same question.
check("_check_product_applicability" in text(PLANNER)
      and "product_not_applicable" in text(PLANNER),
      "[product] planner.py: lost the per-product applicability check — an ECM-"
      "only field requested on DCM (or unscoped) now returns an empty result "
      "instead of a rejection, and the agent reads that as 'no data'")
check("products" in text(ONTOLOGY_PY),
      "[product] ontology.py: the specs no longer carry `products` — per-product "
      "applicability is back to prose, which is what let the bug ship")

if FORMATTER.exists():
    src = text(FORMATTER)
    # The row cap may be applied inline (rows[:cap]) or inside the character
    # budget helper (rows[:row_cap]); both are the same bound. What must never
    # disappear is that SOME slice of rows happens before the model sees them.
    check("max_response_rows" in src
          and ("rows[:cap]" in src or "rows[:row_cap]" in src),
          "[context] formatter.py: the response row cap is gone — this is the "
          "last place before an LLM context and the only hard bound on what one "
          "query can cost in tokens")
    check("next_offset" in src and "truncated" in src,
          "[correctness] formatter.py: a clipped result no longer says so — the "
          "agent cannot tell a complete answer from a cut-off one, and the rows "
          "it did not see become unreachable")
    check("returned_rows" in src,
          "[correctness] formatter.py: returned_rows is gone — row_count alone "
          "cannot distinguish what the query returned from what the model got")

    # SECOND, INDEPENDENT BOUND (added 2026-08-11). The row cap does not bound
    # the PAYLOAD, because row width is not bounded: the tranche object exposes
    # nine VARCHAR2(32767) columns, so one legal row can carry ~250k characters
    # and 100 of them are unbounded in practice. Reported from local runs before
    # this existed: "when the SQL response is too large the LLM fails to parse".
    # Whichever cap binds first must set the SAME truncated/next_offset/paging
    # contract, so the agent pages identically either way.
    check("max_response_chars" in src and "_rows_within_budget" in src,
          "[context] formatter.py: the response CHARACTER cap is gone — the row "
          "cap alone does not bound the payload because row width is unbounded "
          "(nine VARCHAR2(32767) columns on the tranche object). Without it an "
          "over-wide result is unparseable by the model instead of paged.")
    check("_clip_cell" in src,
          "[context] formatter.py: per-cell clipping is gone — a single "
          "pathological cell can exceed the whole budget, and dropping the row "
          "loses its ids. Clip the cell, keep the row.")

if MCPSERVER.exists():
    src = text(MCPSERVER)
    _sig = src.split("def run_bqs_query(", 1)[-1].split(")", 1)[0]
    check("offset" in _sig,
          "[correctness] mcpserver.py: run_bqs_query has no `offset` parameter, "
          "so paging is unreachable from the agent no matter what the engine "
          "supports and what the skill promises")
    check('"offset": offset' in src,
          "[correctness] mcpserver.py: `offset` is accepted but never put in the "
          "BQS request — every page would silently return page 1")

# Both config layers must tell the agent to page with `offset`. Left saying
# only "ask for the next 50", the model's instinct on a truncated result is to
# re-run with a bigger limit — the exact move that exhausts the context.
for _cfg in [ROOT / "adk" / "skills" / "text2sql-capital-markets" / "SKILL.md",
             ROOT / "adk" / "config" / "agents.yaml"]:
    if not _cfg.exists():
        continue
    _c = text(_cfg)
    check("offset" in _c and "next_offset" in _c,
          f"[context] {_cfg.name}: the paging rule no longer names `offset` / "
          f"`next_offset` — the agent is told to offer a next page without being "
          f"told the mechanism, and will reach for a bigger limit instead")
    check("bigger" in _c.lower() and "limit" in _c.lower(),
          f"[context] {_cfg.name}: the prohibition on re-running with a larger "
          f"limit is gone — that is the RESOURCE_EXHAUSTED move")

# ---------------------------------------------------------------------------
# Cross-object field misses, and the hop count.
#
# Observed 2026-08-10 on "top 10 investors by allocation in Energy deals":
# allocation/investor_category are on capital_markets_order, `sector` only on
# capital_markets_deal, and one BQS request cannot span grains. The agent was told only
# "Unknown filter field 'sector' ... Known filters: [...]", which reads as a
# spelling problem — so it discovered all three objects, then made TEN
# run_bqs_query calls, then hit 429 RESOURCE_EXHAUSTED.
# ---------------------------------------------------------------------------
SERVICE = ROOT / "app" / "services" / "domain_query_service.py"
XOBJ_TEST = ROOT / "tests" / "test_cross_object_error.py"

for p in [SERVICE, XOBJ_TEST]:
    check(p.exists(), f"[python] {p.relative_to(ROOT)} is missing")

if SERVICE.exists():
    src = text(SERVICE)
    check("_explain_cross_object" in src,
          "[correctness] domain_query_service.py: a field miss no longer says "
          "WHERE the field lives — 'unknown filter' alone reads as a typo and "
          "the agent guesses again")
    check("_explain_cross_object(e, request)" in src,
          "[correctness] domain_query_service.py: the BQSError handler stopped "
          "routing through the explainer, so the enrichment never runs")
    check("cannot span" in src and "Do NOT" in src,
          "[correctness] domain_query_service.py: the error no longer tells the "
          "agent that one request cannot span grains and must not retry — that "
          "retry loop is what reached 429")

if MCPSERVER.exists():
    src = text(MCPSERVER)
    check("_log_repeat_discovery" in src,
          "[latency] mcpserver.py: repeat-discovery diagnostics are gone. A "
          "catalog costs 0.45s of server time but a whole LLM turn to fetch, and "
          "three of them was most of a minute in the 2026-08-10 trace")

if XOBJ_TEST.exists():
    import subprocess
    rc = subprocess.run([sys.executable, str(XOBJ_TEST)],
                        capture_output=True, text=True).returncode
    check(rc == 0, "[python] test_cross_object_error.py FAILED — run it directly "
                   "to see which explanation regressed")

if PAGING_TEST.exists():
    import subprocess
    rc = subprocess.run([sys.executable, str(PAGING_TEST)],
                        capture_output=True, text=True).returncode
    check(rc == 0, "[python] test_response_paging.py FAILED — run it directly to "
                   "see which response bound regressed")

# ---------------------------------------------------------------------------
# Scope-aware undefined-name check.
#
# mcpserver.py cannot be imported here (fastmcp, uvicorn, mcp), so nothing in
# this gate ever executed a line of it — py_compile only proves it PARSES. That
# gap shipped a real NameError: splitting `_entitlement_gate` into a preflight
# moved `soeid = _resolve_soeid()` into the new function while two log lines in
# the old one still referenced it. It fired only on the success path, so a
# caller WITHOUT entitlements never reached it and a caller WITH them got a 500.
#
# A flat "collect every assignment in the file" check does not catch this — a
# name bound in ANY function looks defined in all of them. symtable gives the
# real per-scope answer.
# ---------------------------------------------------------------------------
import builtins as _builtins
import symtable as _symtable

def _undefined_names(source: str, path: str):
    st = _symtable.symtable(source, path, "exec")
    module_names = {s.get_name() for s in st.get_symbols()}
    found = []

    def walk(tbl, enclosing, trail):
        bound = {s.get_name() for s in tbl.get_symbols()
                 if s.is_assigned() or s.is_parameter() or s.is_imported()}
        for s in tbl.get_symbols():
            name = s.get_name()
            if not s.is_referenced():
                continue
            if name in bound or name in enclosing or name in module_names:
                continue
            if hasattr(_builtins, name) or name.startswith("__"):
                continue
            found.append((".".join(trail + [tbl.get_name()]), name))
        for child in tbl.get_children():
            walk(child, enclosing | bound, trail + [tbl.get_name()])

    walk(st, set(), [])
    return found

for _py in sorted((ROOT / "app").rglob("*.py")):
    if "__pycache__" in _py.parts:
        continue
    try:
        _bad = _undefined_names(text(_py), str(_py))
    except SyntaxError as _exc:
        check(False, f"[python] {_py.relative_to(ROOT)} does not parse: {_exc}")
        continue
    check(not _bad,
          f"[python] {_py.relative_to(ROOT)} references undefined name(s): "
          + ", ".join(f"{scope}() -> {name!r}" for scope, name in _bad)
          + " — this is a NameError at runtime, and these modules cannot be "
            "imported by the gate so nothing else would catch it")

# ---------------------------------------------------------------------------
print(f"\n{passes} checks passed, {len(failures)} failed\n")
if failures:
    print("FAILURES")
    print("--------")
    for f in failures:
        print(f"  - {f}")
    print("\nDO NOT hand these files back until the list is empty.")
    sys.exit(1)
print("Safe to hand back to the POC repo.")
sys.exit(0)
