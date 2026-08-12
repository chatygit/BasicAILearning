"""Fuzzy value/name suggestions for zero-row (or weak) BQS results.

When a governed query returns 0 rows because the agent guessed a value that
does not exactly match the data (wrong case/spelling/word-order, e.g.
sector="Energy" vs "ENERGY", or investor_name "%BLACKROCKK%"), this module
finds the closest *real* values and returns a "did_you_mean" block so the agent
can correct itself on the next call — without any new MCP tool.

Design notes (governed + safe):
  - Candidate retrieval is a read-only, bounded ``SELECT DISTINCT <col>`` probe
    that reuses the existing executor/read-only validator. The agent's guess is
    always parameter-bound (never concatenated).
  - Curated ``values`` in the ontology short-circuit the probe (zero live
    queries) for small fixed enums.
  - Ranking uses rapidfuzz (typos/casing/word-order). We only *suggest* — never
    silently rewrite the query.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import BQSRequest
from .executor import execute
from .sql_builder import BuiltQuery, _build_where

if TYPE_CHECKING:  # avoid import cycles / heavy imports at module load
    from .dialects.base import BaseDialect
    from .ontology import OntologySpec

logger = logging.getLogger(__name__)

# Guardrails.
_MAX_DISTINCT = 200        # never scan/return more than this many candidates
_TOP_K = 5                 # suggestions returned to the agent
_MIN_SCORE = 60            # rapidfuzz score (0-100) floor to be worth showing
# Operators whose value is a scalar string we can fuzzy-match against.
_SUGGESTABLE_OPS = {"eq", "ne", "like", "in", "not_in"}

# Disambiguation guardrails (over-match on entity-name fields).
_DISAMBIG_OPS = {"like", "eq", "in"}   # value-bearing name predicates
_DISAMBIG_MAX = 25                     # cap the listed distinct names


@dataclass
class _Candidate:
    field: str          # business filter name
    column: str         # physical column (server-side only)
    value: str          # the agent's guessed value (raw)


def _stem(value: str) -> str:
    """Loosen a guess into a broad SQL LIKE stem for candidate retrieval.

    We strip LIKE wildcards and punctuation and keep the longest alphanumeric
    run so a typo near the end (e.g. 'BLACKROCKK') still retrieves 'BLACKROCK…'.
    Falls back to the first few chars. The result is only ever parameter-bound.
    """
    core = value.strip().strip("%").upper()
    tokens = re.findall(r"[A-Z0-9]+", core)
    if not tokens:
        return ""
    longest: str = max(tokens, key=len)
    # Use a generous prefix of the longest token so near-miss typos still hit.
    return longest[: max(3, len(longest) - 2)]


def _suggestable_scalar(value) -> str | None:
    """Return a single string value to match, or None if not applicable."""
    if isinstance(value, str):
        v = value.strip()
        return v or None
    if isinstance(value, (list, tuple)) and len(value) == 1 and isinstance(value[0], str):
        return value[0].strip() or None
    return None


def collect_candidates(req: BQSRequest, spec: "OntologySpec") -> list[_Candidate]:
    """Find request filters that are suggestable and carry a scalar string."""
    out: list[_Candidate] = []
    for f in req.filters:
        fs = spec.filters.get(f.field)
        if fs is None or not fs.suggestable:
            continue
        if f.op.value not in _SUGGESTABLE_OPS:
            continue
        val = _suggestable_scalar(f.value)
        if val is None:
            continue
        out.append(_Candidate(field=f.field, column=fs.column, value=val))
    return out


def _rank(guess: str, choices: list[str]) -> list[dict]:
    """Rank real values against the guess using rapidfuzz (token-set + WRatio).

    Matching is case-insensitive (processor lowercases both sides) so guesses
    like 'Energy'/'ecm' match real values 'ENERGY'/'ECM'.
    """
    from rapidfuzz import fuzz, process, utils

    guess_norm = guess.strip().strip("%")
    scored = process.extract(
        guess_norm,
        choices,
        scorer=fuzz.WRatio,
        processor=utils.default_process,  # lowercases + trims + strips non-alnum
        limit=_TOP_K,
    )
    return [
        {"value": value, "score": round(score, 1)}
        for value, score, _idx in scored
        if score >= _MIN_SCORE
    ]


def _build_distinct_probe(
    spec: "OntologySpec",
    column: str,
    stem: str,
    dialect: "BaseDialect",
    plan=None,
    exclude_fields: set[str] | None = None,
) -> tuple[str, dict]:
    """Build a bounded, read-only DISTINCT probe. Guess stem is bound as param.

    PERFORMANCE + TRUTH: the probe is SCOPED with the plan's WHERE minus every
    suggestable guess (``exclude_fields``), the same way the disambiguation
    probe reuses _build_where. The governed scope (product/entitlement, dates,
    computed/derived filters) pushes down, so the probe is fast AND only offers
    values that exist WITHIN the asked scope — an unscoped probe used to cost a
    full-view DISTINCT scan per suggestable filter (measured 34.89s on the
    scoped analog's predecessor) and could suggest values from the product the
    caller never asked for. All guesses are excluded together because excluding
    only the probed one would let a second bad guess zero out every probe.
    """
    col = dialect.quote_ident(column)
    base = dialect.quote_ident(spec.base_view)
    params: dict = {}
    if plan is not None:
        scope = _build_where(plan, dialect, params, exclude_fields=exclude_fields)
    else:
        scope = ""
    if stem:
        params["stem"] = f"%{stem}%"
        # Case-insensitive contains match on the loosened stem.
        pred = f"UPPER({col}) LIKE {dialect.placeholder(0, 'stem')}"
    else:
        pred = f"{col} IS NOT NULL"
    where = f"{scope} AND {pred}" if scope else f" WHERE {pred}"
    sql = (
        f'SELECT DISTINCT {col} AS "value" FROM {base}{where} '
        f"ORDER BY 1 {dialect.limit_clause(_MAX_DISTINCT)}"
    )
    return sql, params


def _is_same_value(guess: str, top_choice: str) -> bool:
    """True when the top-ranked real value IS the agent's guess (case/wildcard
    insensitive) — i.e. the guess was right and something ELSE zeroed the rows."""
    return guess.strip().strip("%").upper() == top_choice.strip().upper()


def build_suggestions(
    req: BQSRequest,
    spec: "OntologySpec",
    dialect: "BaseDialect",
    plan=None,
) -> list[dict]:
    """Return a list of suggestion blocks (one per suggestable filter guess).

    Best-effort: any probe failure is swallowed (logged) so suggestions never
    break the primary (already-successful) response.
    """
    candidates = collect_candidates(req, spec)
    if not candidates:
        return []
    # All guesses come out of the probe scope together — see _build_distinct_probe.
    guessed_fields = {c.field for c in candidates}

    suggestions: list[dict] = []
    for c in candidates:
        try:
            fs = spec.filters[c.field]
            # 1) Curated values short-circuit the DB probe entirely.
            if fs.values:
                choices = [str(v) for v in fs.values]
            else:
                stem = _stem(c.value)
                sql, params = _build_distinct_probe(
                    spec, c.column, stem, dialect,
                    plan=plan, exclude_fields=guessed_fields,
                )
                _cols, rows = execute(spec, BuiltQuery(sql=sql, params=params), dialect)
                choices = [str(r[0]) for r in rows if r and r[0] is not None]
            if not choices:
                continue
            ranked = _rank(c.value, choices)
            if not ranked:
                continue
            if _is_same_value(c.value, ranked[0]["value"]):
                # The guess is a REAL value (curated enums land here — probes
                # can't fix those — and so does the gate-injected product
                # filter). Retrying the identical request would just pay the
                # query again: the zero rows came from the OTHER constraints.
                hint = (
                    f"'{c.value}' is a real value on '{c.field}' — the 0 rows "
                    f"come from your OTHER constraints (date window, product, "
                    f"or another filter), not this one. Do NOT retry the same "
                    f"request; widen or drop one of the other constraints, or "
                    f"tell the user nothing matches in that scope."
                )
            else:
                hint = (
                    f"0 rows matched '{c.value}' on '{c.field}'. The values "
                    f"above are real values from the data — retry with one "
                    f"of them (exact spelling/case)."
                )
            suggestions.append(
                {
                    "field": c.field,
                    "your_value": c.value,
                    "did_you_mean": [r["value"] for r in ranked],
                    "scored": ranked,
                    "hint": hint,
                }
            )
        except Exception as e:  # noqa: BLE001 - suggestions are best-effort
            logger.warning(
                "Suggestion probe failed for field=%s: %s", c.field, e
            )
            continue
    return suggestions


# ---------------------------------------------------------------------------
# Over-match disambiguation for entity-name filters (non-zero results).
# ---------------------------------------------------------------------------


@dataclass
class _EntityFilter:
    field: str          # business filter name
    column: str         # physical name column (server-side only)
    op: str             # like / eq / in
    value: object       # raw value (str for like/eq; list for in)
    id_column: str = ""  # physical id paired with the name (may be unset)


def _collect_entity_filters(
    req: BQSRequest, spec: "OntologySpec"
) -> list[_EntityFilter]:
    """Entity-name filters carrying a value predicate we can disambiguate."""
    out: list[_EntityFilter] = []
    for f in req.filters:
        fs = spec.filters.get(f.field)
        if fs is None or not getattr(fs, "entity_name", False):
            continue
        if f.op.value not in _DISAMBIG_OPS:
            continue
        if f.value is None:
            continue
        out.append(
            _EntityFilter(
                field=f.field,
                column=fs.column,
                op=f.op.value,
                value=f.value,
                id_column=getattr(fs, "entity_id_column", "") or "",
            )
        )
    return out


def _build_entity_distinct_probe(
    spec: "OntologySpec", ef: _EntityFilter, dialect: "BaseDialect", plan=None
) -> tuple[str, dict]:
    """DISTINCT of the matched entity names, scoped exactly like the main query.

    ``plan`` is the QueryPlan the answer was built from. Reusing its WHERE via
    the SAME renderer the main SQL uses is both a correctness and a latency fix:

      - LATENCY. Scoping by the entity predicate ALONE drops the date range and
        the product, so the probe scans the whole view for all time and both
        products. Measured on "how much did Blackrock invest in ECM deals in
        2025": the main query ran in 6.11s and this probe took 34.89s — 85% of
        a 41s tool call, for a list the user did not need to be that wide.
      - CORRECTNESS. The hand-rolled predicate was case-SENSITIVE while the main
        query wraps both sides in UPPER(), so the two could match different
        rows; and an unscoped probe offers the user entities that contributed
        nothing to the number they are looking at.

    The agent's value is always parameter-bound (never concatenated).
    """
    col = dialect.quote_ident(ef.column)
    base = dialect.quote_ident(spec.base_view)
    params: dict = {}

    if plan is not None:
        where = _build_where(plan, dialect, params)
        where = f"{where} AND {col} IS NOT NULL" if where else f" WHERE {col} IS NOT NULL"
    else:
        # Fallback: entity predicate only. Kept so the helper stays callable
        # without a plan, but it is the slow, unscoped shape described above.
        if ef.op == "in" and isinstance(ef.value, (list, tuple)):
            names = []
            for j, v in enumerate(ef.value):
                pname = f"d{j}"
                params[pname] = v
                names.append(dialect.placeholder(0, pname))
            where = f" WHERE {col} IN ({', '.join(names)})"
        elif ef.op == "like":
            params["d"] = str(ef.value)
            where = f" WHERE {col} LIKE {dialect.placeholder(0, 'd')}"
        else:  # eq
            params["d"] = str(ef.value)
            where = f" WHERE {col} = {dialect.placeholder(0, 'd')}"
        where = f"{where} AND {col} IS NOT NULL"

    # Return the paired id when the ontology declares one. A name is not
    # unique, so a list of bare names is something the user has to RETYPE and
    # may still get wrong; name + id is a handle they can paste or pick.
    select = f'DISTINCT {col} AS "value"'
    if ef.id_column:
        select += f', {dialect.quote_ident(ef.id_column)} AS "entity_id"'
    sql = (
        f"SELECT {select} FROM {base}{where} "
        f"ORDER BY 1 {dialect.limit_clause(_DISAMBIG_MAX + 1)}"
    )
    return sql, params


def _order_by_closeness(guess: str, names: list[str]) -> list[str]:
    """Optional: order matched names by closeness to a concrete guess token.

    Only meaningful when the guess is a real name stem (e.g. '%BLACKROCK%'),
    not a broad fragment ('%BLACK%'). rapidfuzz is used only for ordering here —
    it is NOT required for disambiguation and never filters the list.
    """
    token = _stem(guess)
    if not token or len(token) < 4:
        return names  # too broad to rank meaningfully
    try:
        from rapidfuzz import fuzz, utils

        return sorted(
            names,
            key=lambda n: fuzz.WRatio(guess.strip("%"), n, processor=utils.default_process),
            reverse=True,
        )
    except Exception:  # noqa: BLE001 - ordering is best-effort
        return names


def build_disambiguation(
    req: BQSRequest,
    spec: "OntologySpec",
    dialect: "BaseDialect",
    result_rows: list[dict] | None = None,
    plan=None,
) -> list[dict]:
    """When an entity-name filter matched MORE THAN ONE distinct entity, return
    a disambiguation block so the agent can re-run with a single entity.

    Cheap: if the name field is already a selected dimension in the result, the
    distinct names are counted from the returned rows (no extra query);
    otherwise one bounded DISTINCT probe is run. Best-effort — never fatal.
    """
    entity_filters = _collect_entity_filters(req, spec)
    if not entity_filters:
        return []

    blocks: list[dict] = []
    for ef in entity_filters:
        try:
            names: list[str] = []
            ids: dict[str, str] = {}
            # 1) Free path: the name field is a selected dimension -> use rows.
            #    PROJECTING the name field you filter on therefore makes
            #    disambiguation cost nothing. Worth doing every time.
            if result_rows and ef.field in (req.dimensions or []):
                seen = {
                    str(r[ef.field])
                    for r in result_rows
                    if r.get(ef.field) is not None
                }
                names = sorted(seen)
            else:
                # 2) One bounded DISTINCT probe scoped by the same predicate,
                #    returning (name, id) when the ontology pairs an id column.
                sql, params = _build_entity_distinct_probe(spec, ef, dialect, plan)
                _cols, rows = execute(spec, BuiltQuery(sql=sql, params=params), dialect)
                for r in rows:
                    if not r or r[0] is None:
                        continue
                    name = str(r[0])
                    names.append(name)
                    if ef.id_column and len(r) > 1 and r[1] is not None:
                        ids.setdefault(name, str(r[1]))

            if len(names) <= 1:
                continue  # single (or no) entity -> unambiguous, no nag

            guess = ef.value if isinstance(ef.value, str) else ""
            ordered = _order_by_closeness(guess, names)[:_DISAMBIG_MAX]
            # Always objects, so the shape is the same whether or not an id was
            # available. `id` is null only when the ontology declares no pairing
            # (or on the free path, where the agent already holds its own rows).
            matched = [{"name": n, "id": ids.get(n)} for n in ordered]
            has_ids = any(m["id"] for m in matched)
            blocks.append(
                {
                    "field": ef.field,
                    "your_value": ef.value,
                    "matched_multiple": matched,
                    "truncated": len(names) > _DISAMBIG_MAX,
                    "hint": (
                        f"Your filter on '{ef.field}' matched multiple distinct "
                        f"entities, so the result blends them together. Show them "
                        f"to the user as a NUMBERED list"
                        + (" with each entity's id beside its name, "
                           if has_ids else ", ")
                        + "and invite them to reply with a number"
                        + (" or paste an id" if has_ids else "")
                        + ". To isolate one, re-run filtered to that single "
                        + ("id." if has_ids else "exact name.")
                    ),
                }
            )
        except Exception as e:  # noqa: BLE001 - disambiguation is best-effort
            logger.warning(
                "Disambiguation probe failed for field=%s: %s", ef.field, e
            )
            continue
    return blocks
