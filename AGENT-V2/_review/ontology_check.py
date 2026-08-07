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
DEAL = ONT / "ecm_dcm_deal.yaml"
TRANCHE = ONT / "ecm_dcm_tranche.yaml"
ORDER = ONT / "ecm_dcm_order.yaml"
ENTITY = ONT / "ecm_dcm_entity.yaml"
SKILL = ROOT / "adk" / "skills" / "text2sql-ecm-dcm" / "SKILL.md"
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
for path in [TRANCHE, SKILL, AGENTS]:
    check(has(path, "token-less") or has(path, "NO token"),
          f"[bnd] {path.name}: lost the fact that bill_and_deliver is "
          f"token-less — passing it a token is not the server's recipe")
    # Must be syndicate_member PAIRED WITH bill_and_deliver in the same recipe —
    # a bare mention of syndicate_member elsewhere in the file is not enough.
    recipe = re.search(r"[Cc]iti[ -]?non-B&D.{0,400}", text(path), re.S)
    window = " ".join(re.sub(r"[`*]", "", recipe.group(0)).split()) if recipe else ""
    check("syndicate_member" in window and "bill_and_deliver" in window,
          f"[bnd] {path.name}: the 'Citi non-B&D' recipe no longer pairs "
          f"syndicate_member with bill_and_deliver — that is the server's own "
          f"documented composite")
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
    ("product scoping", "ALWAYS set a `product` filter"),
    ("units doctrine", "never total across"),
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
check("text_to_sql_mcp" in text(TOOLS),
      "[agent] agents.yaml references tool 'text_to_sql_mcp', which tools.yaml "
      "does not define")

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

for p in [MCPSERVER, PLANNER, MODELS, BUILDER, SCOPE_TEST]:
    check(p.exists(), f"[python] {p.relative_to(ROOT)} is missing")

if MCPSERVER.exists():
    src = text(MCPSERVER)
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
    check(src.count("FAIL-OPEN (undecided)") == 3,
          f"[python] mcpserver.py: expected 3 FAIL-OPEN markers, found "
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
          "landmine note — an allow-list still naming 'ecm_dcm' silently "
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
check(has(SKILL, "Truncation is not reported"),
      "[contract] SKILL.md lost the truncation rule — there is no `truncated` "
      "flag and no `limit` echo, so row_count == limit must be read as "
      "'possibly more rows'")

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
