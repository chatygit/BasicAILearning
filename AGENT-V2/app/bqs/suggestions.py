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
from .sql_builder import BuiltQuery

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
    spec: "OntologySpec", column: str, stem: str, dialect: "BaseDialect"
) -> tuple[str, dict]:
    """Build a bounded, read-only DISTINCT probe. Guess stem is bound as param."""
    col = dialect.quote_ident(column)
    base = dialect.quote_ident(spec.base_view)
    params: dict = {}
    where = ""
    if stem:
        params["stem"] = f"%{stem}%"
        # Case-insensitive contains match on the loosened stem.
        where = f" WHERE UPPER({col}) LIKE {dialect.placeholder(0, 'stem')}"
    else:
        where = f" WHERE {col} IS NOT NULL"
    sql = (
        f'SELECT DISTINCT {col} AS "value" FROM {base}{where} '
        f"ORDER BY 1 {dialect.limit_clause(_MAX_DISTINCT)}"
    )
    # PERFORMANCE: this probe is UNSCOPED — it carries neither the request's
    # product filter nor its date range, and UPPER(col) defeats a plain index.
    # So a 0-row query costs a full-view DISTINCT scan PER suggestable filter,
    # on top of the original query. An unhelpful guess is the expensive path.
    return sql, params


def build_suggestions(
    req: BQSRequest,
    spec: "OntologySpec",
    dialect: "BaseDialect",
) -> list[dict]:
    """Return a list of suggestion blocks (one per suggestable filter guess).

    Best-effort: any probe failure is swallowed (logged) so suggestions never
    break the primary (already-successful) response.
    """
    candidates = collect_candidates(req, spec)
    if not candidates:
        return []

    suggestions: list[dict] = []
    for c in candidates:
        try:
            fs = spec.filters[c.field]
            # 1) Curated values short-circuit the DB probe entirely.
            if fs.values:
                choices = [str(v) for v in fs.values]
            else:
                stem = _stem(c.value)
                sql, params = _build_distinct_probe(spec, c.column, stem, dialect)
                _cols, rows = execute(spec, BuiltQuery(sql=sql, params=params), dialect)
                choices = [str(r[0]) for r in rows if r and r[0] is not None]
            if not choices:
                continue
            ranked = _rank(c.value, choices)
            if not ranked:
                continue
            suggestions.append(
                {
                    "field": c.field,
                    "your_value": c.value,
                    "did_you_mean": [r["value"] for r in ranked],
                    "scored": ranked,
                    "hint": (
                        f"0 rows matched '{c.value}' on '{c.field}'. The values "
                        f"above are real values from the data — retry with one "
                        f"of them (exact spelling/case)."
                    ),
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
            _EntityFilter(field=f.field, column=fs.column, op=f.op.value, value=f.value)
        )
    return out


def _build_entity_distinct_probe(
    spec: "OntologySpec", ef: _EntityFilter, dialect: "BaseDialect"
) -> tuple[str, dict]:
    """DISTINCT of the matched entity names, scoped by the SAME value predicate.

    The agent's value is always parameter-bound (never concatenated).
    """
    col = dialect.quote_ident(ef.column)
    base = dialect.quote_ident(spec.base_view)
    params: dict = {}
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
    sql = (
        f'SELECT DISTINCT {col} AS "value" FROM {base}{where} '
        f"AND {col} IS NOT NULL ORDER BY 1 {dialect.limit_clause(_DISAMBIG_MAX + 1)}"
    )
    # The extra AND after a WHERE is safe because `where` always starts a WHERE.
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
                # 2) One bounded DISTINCT probe scoped by the same predicate.
                sql, params = _build_entity_distinct_probe(spec, ef, dialect)
                _cols, rows = execute(spec, BuiltQuery(sql=sql, params=params), dialect)
                names = [str(r[0]) for r in rows if r and r[0] is not None]

            if len(names) <= 1:
                continue  # single (or no) entity -> unambiguous, no nag

            guess = ef.value if isinstance(ef.value, str) else ""
            ordered = _order_by_closeness(guess, names)[:_DISAMBIG_MAX]
            blocks.append(
                {
                    "field": ef.field,
                    "your_value": ef.value,
                    "matched_multiple": ordered,
                    "truncated": len(names) > _DISAMBIG_MAX,
                    "hint": (
                        f"Your filter on '{ef.field}' matched multiple distinct "
                        f"entities, so the result blends them together. To isolate "
                        f"one, re-run with a single exact name from the list above."
                    ),
                }
            )
        except Exception as e:  # noqa: BLE001 - disambiguation is best-effort
            logger.warning(
                "Disambiguation probe failed for field=%s: %s", ef.field, e
            )
            continue
    return blocks
