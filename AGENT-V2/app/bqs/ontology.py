"""Business Ontology + Metadata catalog with hot-reload.

Loads one YAML per data source from the ontology directory. Each file maps
business-friendly names to the real physical schema and pins a dialect and
connection. The agent never sees this mapping — it only receives business
names via the discovery tool.

Hot-reload: files are re-read when their mtime changes, so governance
changes take effect without redeploying the server.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from .models import BQSError, FilterOperator

logger = logging.getLogger(__name__)


class Dialect(str, Enum):
    POSTGRES = "postgres"
    ORACLE = "oracle"
    TRINO = "trino"


class Aggregation(str, Enum):
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    MIN = "MIN"
    MAX = "MAX"


class ConnectionSpec(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None      # postgres dbname
    service_name: Optional[str] = None  # oracle service
    user: Optional[str] = None
    # CyberArk nickname used to fetch the read-only password.
    cyberark_fid: Optional[str] = None
    sslmode: str = "require"
    read_only_role: Optional[str] = None
    # Trino/Starburst: catalog + schema for the connector session. When set,
    # the executor routes through starburst_connector (env-configured).
    catalog: Optional[str] = None
    schema_: Optional[str] = Field(default=None, alias="schema")

    model_config = {"populate_by_name": True}


class MetricSpec(BaseModel):
    column: str
    aggregation: Aggregation = Aggregation.SUM
    description: str = ""
    # When true, the metric column is cast to a numeric type before value
    # aggregation (SUM/AVG/MIN/MAX). Needed for governed views that store
    # numeric measures as strings (e.g. Trino VARCHAR columns).
    numeric: bool = False
    # When true, the metric MEASURES the number of elements in a pipe-delimited
    # list column (e.g. the syndicate member list) via the dialect's list_count,
    # then aggregates that per-row count (typically MAX to collapse to the deal
    # grain). Enables "deals with N+ syndicates" through a HAVING threshold.
    list_count: bool = False
    # Optional grain-defining columns. When set, the metric column is
    # deduplicated to one row per distinct dedup_key (plus any selected
    # dimensions) BEFORE aggregating — e.g. SUM(TRANCHE_SIZE) counted once per
    # DEAL_ID even though base rows are per-investor. Prevents double-counting.
    dedup_key: list[str] = Field(default_factory=list)
    # Governed performance guardrail: business filter-names that MUST be present
    # on any request using this metric. Heavy metrics (e.g. deduplicated numeric
    # aggregations that scan the whole view) require a scoping filter such as
    # 'product' so the DB can prune instead of doing a full scan/dedup.
    requires_filters: list[str] = Field(default_factory=list)


class DimensionSpec(BaseModel):
    column: str
    description: str = ""


class FilterSpec(BaseModel):
    column: str
    operators: list[FilterOperator] = Field(default_factory=list)
    description: str = ""
    # When true, this filter's column is a bounded, suggestable field: on a
    # 0-row result the server may probe DISTINCT values and fuzzy-rank the
    # agent's guess against them to return "did_you_mean" suggestions. Set on
    # categorical fields (sector, currency, ...) and entity-name fields
    # (issuer_name, ...). Leave false for ids, dates and free numerics.
    suggestable: bool = False
    # Optional curated value list. When present, suggestions are ranked against
    # these instead of a live DISTINCT probe (zero live queries). Best for small
    # fixed enums (product, product_class).
    values: list[str] = Field(default_factory=list)
    # When true, this filter targets a high-cardinality free-text ENTITY name
    # (issuer/investor/deal). A non-zero result whose matched names span more
    # than one distinct entity triggers a "disambiguation" block so the agent
    # can pick a single entity (the disambiguation half of the old
    # entity_search). Distinct from `suggestable`, which handles 0-row typos.
    entity_name: bool = False
    # Physical id column that PAIRS with this entity name (investor_gp_id for
    # investor_name, gfcid for issuer_name, deal_id for deal_name, ...). When
    # set, the disambiguation probe returns (name, id) pairs instead of bare
    # names, so the agent can show a stable handle and the user can pick one.
    # A name is NOT unique — offering a user a list of names to retype is both
    # ambiguous and unusable. Only meaningful alongside `entity_name: true`.
    entity_id_column: str = ""
    # When true, string comparisons for this filter are case-insensitive: the
    # column and the bound value are both wrapped in UPPER() for the text
    # operators (eq/ne/like/in/not_in). Set on free-text/categorical columns
    # whose stored casing varies (names, industries, countries) so a
    # case-mismatched guess still matches instead of silently returning 0 rows.
    # Leave false for ids, dates and numeric columns.
    case_insensitive: bool = False


class AliasSpec(BaseModel):
    """A governed business token -> one or more canonical codes.

    The agent passes a business token (e.g. "citi"); the server resolves it to
    the governed codes here and composes the regex pattern. No unvetted agent
    text ever reaches the SQL — only these allow-listed codes.
    """

    codes: list[str] = Field(default_factory=list)
    description: str = ""


class ComputedFilterSpec(BaseModel):
    """A governed, alias-resolved regex filter over a physical column.

    Covers complex predicates (e.g. broker anchoring on pipe-delimited lists,
    Bill-and-Deliver truthy matching) without exposing SQL to the agent. The
    agent only supplies a business token; the server:
      1. resolves the token to canonical code(s) via `aliases`,
      2. regex-escapes each code and substitutes it into `pattern_template`
         (which owns the anchor logic, e.g. '(^| \\| ){value}'),
      3. OR-joins the per-code patterns and binds the result as a parameter,
      4. renders a dialect-specific regexp predicate.

    `pattern_template` is dialect-agnostic POSIX-style and MUST contain the
    literal token '{value}' where the (escaped) code is substituted.
    """

    column: str
    pattern_template: str = Field(
        ...,
        description="Regex with a single '{value}' slot for the resolved code.",
    )
    aliases: dict[str, AliasSpec] = Field(default_factory=dict)
    # When set, the agent's token is ignored and these fixed codes are used
    # (e.g. a Bill-and-Deliver truthy-token match with no user entity).
    fixed_codes: list[str] = Field(default_factory=list)
    description: str = ""


class UnsupportedIntentSpec(BaseModel):
    """A governed, unanswerable intent for this source.

    Surfaced in discovery so the agent can refuse early, and enforced
    server-side: if a request carries this intent id, the query is rejected
    with `user_message` instead of guessing a proxy column.
    """

    patterns: list[str] = Field(default_factory=list)
    reason: str = ""
    user_message: str = ""


class DerivedFilterSpec(BaseModel):
    """A governed, server-authored predicate over one or more physical columns.

    Covers conditions the agent can't express with a single value filter — most
    notably column-vs-column comparisons (e.g. settlement currency differs from
    the deal currency). The predicate template is written by the governance
    author and references business dimension/filter NAMES as ``{name}`` tokens;
    the server resolves each token to its physical column and quotes it. No
    agent-supplied value ever enters the SQL — the agent only names the filter.
    """

    predicate: str = Field(
        ...,
        description="SQL predicate template with {business_name} column tokens.",
    )
    description: str = ""


class AsOfDateSpec(BaseModel):
    """Governed 'data available till' date for time-relative period columns.

    The physical view pre-computes CYTD/PYTD relative to this date. Declaring
    the availability-view query here lets the server fetch the real as_of_date
    and return it on every query so the agent renders an accurate
    ``Data as of: <Month YYYY>`` header and absolute-year period labels — never
    a guessed month/year. Governed (YAML), never hard-coded in Python.
    """

    query: str = Field(
        ...,
        description="Read-only SQL returning a single as_of_date value.",
    )


class OntologySpec(BaseModel):
    """A single governed data source definition."""

    source: str
    version: str = "1"
    dialect: Dialect
    connection: ConnectionSpec
    # Business view name -> physical schema-qualified relation.
    base_view: str = Field(..., description="Physical schema.table/view to query.")
    # Object grain: the business dimension NAMES whose combination makes one row
    # of ``base_view`` unique (e.g. [product, deal_id] for the deal object). This
    # moves grain from prompt discipline into structure: it is surfaced verbatim
    # in discovery so the agent routes to the right object, and it lets the
    # builder reason about uniqueness instead of relying on per-metric dedup_key.
    # For a grain-aligned view (one physical row per grain) value metrics need no
    # dedup_key — the row is already unique. Declared in business names so it can
    # be shown to the agent without leaking physical columns.
    grain: list[str] = Field(default_factory=list)
    # Optional governed availability-date query. When set, the server fetches the
    # latest as_of_date and returns it on every query for this source.
    as_of_date: Optional[AsOfDateSpec] = None
    metrics: dict[str, MetricSpec] = Field(default_factory=dict)
    dimensions: dict[str, DimensionSpec] = Field(default_factory=dict)
    filters: dict[str, FilterSpec] = Field(default_factory=dict)
    computed_filters: dict[str, ComputedFilterSpec] = Field(default_factory=dict)
    derived_filters: dict[str, DerivedFilterSpec] = Field(default_factory=dict)
    unsupported_intents: dict[str, UnsupportedIntentSpec] = Field(
        default_factory=dict
    )
    # Default date dimension used for time_grain bucketing when the request
    # does not name one explicitly.
    default_time_dimension: Optional[str] = None
    max_limit: int = 10000
    query_timeout_seconds: int = 30
    # Optional free-text guidance surfaced verbatim in discovery to help the
    # agent build a valid request (how-to, gotchas). Governed, not physical.
    usage_notes: list[str] = Field(default_factory=list)
    # Optional worked examples: natural-language question -> a ready-to-run
    # run_bqs_query request body. Teaches the agent the exact request shape.
    examples: list[dict] = Field(default_factory=list)
    # Optional per-source request-building recipe. Appended AFTER the generic,
    # source-agnostic instructions so domain guidance (which source to pick,
    # mandatory scoping filters, gotchas) lives with the data, not in code.
    how_to_use: list[str] = Field(default_factory=list)

    @staticmethod
    def _generic_how_to_use() -> list[str]:
        """Source-agnostic instructions for building a request.

        Domain-specific guidance (which metric/filter to use, mandatory scoping,
        gotchas) belongs in each ontology's ``how_to_use`` / ``usage_notes`` /
        ``examples`` — surfaced verbatim by discovery — never hard-coded here.
        """
        return [
            "Call run_bqs_query with a JSON body using ONLY the business names "
            "listed below for THIS source. Never invent names, never pass "
            "physical column names, and never reuse names from another source.",
            "'source': if discovery returned more than one source, you MUST pass "
            "the exact 'source' whose catalog contains your chosen metric. If "
            "only one source exists you may omit it.",
            "Required field: 'metric'. Pick exactly ONE metric per call (the "
            "number you want to compute).",
            "Group by putting dimension names in 'dimensions' (a list).",
            "Filter with 'filters': a list of {\"field\", \"op\", \"value\"}. "
            "'field' must be a filter name below and 'op' must be one of its "
            "allowed operators.",
            "For a date range use two filters with op 'gte' and 'lt', or a "
            "single 'between' with a 2-item [start, end] list.",
            "To rank/sort, use 'order': [{\"field\", \"direction\"}] where "
            "'field' is the metric or a selected dimension, and set 'limit' for "
            "'top N' questions (e.g. order desc by the metric, limit 10).",
            "For a filter that lists a 'values' catalog, pass one of those exact "
            "values. For a filter marked entity_name, match by name with op "
            "'like' and value '%NAME%' (case-insensitive on the server).",
            "Read this source's 'usage_notes' and 'examples' — they carry the "
            "domain-specific recipe and gotchas. If a call fails, read the "
            "returned 'message'; it names the exact valid names/operators — fix "
            "that one field and retry.",
        ]

    def discovery(self) -> dict:
        """Business-facing catalog. Contains NO physical schema names."""
        return {
            "source": self.source,
            "version": self.version,
            "grain": list(self.grain),
            "how_to_use": self._generic_how_to_use() + list(self.how_to_use),
            "usage_notes": list(self.usage_notes),
            "examples": list(self.examples),
            # How the server enriches responses so the agent can self-correct
            # without any extra tool (surfaced here, not only in the tool doc).
            "response_features": {
                "suggestions": (
                    "If a query returns 0 rows because a filter VALUE didn't "
                    "match the data (wrong case/spelling), the response includes "
                    "a 'suggestions' block with 'did_you_mean' real values — "
                    "retry with one of those exact values."
                ),
                "disambiguation": (
                    "If a NON-empty result came from a name filter that matched "
                    "multiple distinct entities (e.g. investor_name like "
                    "'%BLACK%'), the response includes a 'disambiguation' block "
                    "listing them — re-run with one exact name to isolate one."
                ),
                **(
                    {
                        "as_of_date": (
                            "Every query response includes an 'as_of_date' (ISO "
                            "date) — the latest date the data is available till. "
                            "Time-relative period columns (CYTD/PYTD and the "
                            "monthly columns) are computed relative to it. Render "
                            "the 'Data as of: <Month YYYY>' header and all "
                            "absolute-year period labels FROM this date — never "
                            "from today's date or a guess."
                        )
                    }
                    if self.as_of_date is not None
                    else {}
                ),
            },
            "default_time_dimension": self.default_time_dimension,
            "max_limit": self.max_limit,
            "metrics": {
                name: {"aggregation": m.aggregation.value, "description": m.description}
                for name, m in self.metrics.items()
            },
            "dimensions": {
                name: {"description": d.description}
                for name, d in self.dimensions.items()
            },
            "filters": {
                name: {
                    "operators": [op.value for op in f.operators],
                    "description": f.description,
                    # Surface curated allowed values (e.g. product = ECM/DCM) so
                    # the agent uses exact values and avoids a 0-row guess.
                    **({"values": list(f.values)} if f.values else {}),
                    # Hint that this is a free-text name field: filter by name
                    # with op 'like' and '%NAME%'; over-matches get disambiguated.
                    **({"entity_name": True} if f.entity_name else {}),
                }
                for name, f in self.filters.items()
            },
            "computed_filters": {
                name: {
                    "description": c.description,
                    # Expose the accepted business tokens so the agent knows
                    # what values it may pass — never the SQL/regex behind them.
                    "allowed_tokens": sorted(c.aliases) if c.aliases else [],
                    "needs_token": not c.fixed_codes,
                }
                for name, c in self.computed_filters.items()
            },
            "derived_filters": {
                name: {"description": d.description}
                for name, d in self.derived_filters.items()
            },
            "unsupported_intents": {
                name: {
                    "patterns": u.patterns,
                    "user_message": u.user_message,
                }
                for name, u in self.unsupported_intents.items()
            },
        }


class _LoadedOntology:
    __slots__ = ("spec", "mtime", "path")

    def __init__(self, spec: OntologySpec, mtime: float, path: Path) -> None:
        self.spec = spec
        self.mtime = mtime
        self.path = path


class OntologyRegistry:
    """Thread-safe registry of ontologies with mtime-based hot-reload."""

    def __init__(
        self,
        ontology_dir: str | Path,
        enabled_sources: set[str] | None = None,
    ) -> None:
        self._dir = Path(ontology_dir)
        self._lock = threading.RLock()
        self._by_source: dict[str, _LoadedOntology] = {}
        # Allow-list of source ids that may be registered/served. When set, any
        # ontology whose `source` is not listed is ignored — so the agent can
        # only ever query the enabled use case(s) (e.g. ecm_dcm / Trino).
        self._enabled_sources = enabled_sources
        self.reload()
        self._log_enablement_summary()

    def _log_enablement_summary(self) -> None:
        """Log a single, explicit enabled-vs-disabled summary at startup.

        The per-file lines emitted during reload() are incremental and noisy
        (disabled files are re-evaluated on every reload); this classifies every
        ontology on disk once so the log states plainly which sources are served.
        """
        enabled: list[str] = []
        disabled: list[str] = []
        for path in sorted(self._dir.glob("*.y*ml")):
            try:
                src = self._load_file(path).source
            except Exception as e:  # noqa: BLE001 - already reported by reload()
                logger.debug("Enablement summary skipped unreadable %s: %s", path.name, e)
                continue
            if self._enabled_sources is None or src in self._enabled_sources:
                enabled.append(src)
            else:
                disabled.append(src)
        configured = (
            "* (all)"
            if self._enabled_sources is None
            else ",".join(sorted(self._enabled_sources))
        )
        logger.info("Ontology enablement: BQS_ENABLED_SOURCES=%s", configured)
        logger.info(
            "Ontology ENABLED sources (%d): %s",
            len(enabled),
            ", ".join(sorted(enabled)) or "(none)",
        )
        logger.info(
            "Ontology DISABLED sources (%d): %s",
            len(disabled),
            ", ".join(sorted(disabled)) or "(none)",
        )
        if self._enabled_sources is not None:
            missing = sorted(self._enabled_sources - set(enabled))
            if missing:
                logger.warning(
                    "Ontology sources requested via BQS_ENABLED_SOURCES but NOT "
                    "found on disk (%d): %s",
                    len(missing),
                    ", ".join(missing),
                )

    def _load_file(self, path: Path) -> OntologySpec:
        with path.open(mode="r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        return OntologySpec.model_validate(raw)

    def _loaded_for_path(self, path: Path) -> _LoadedOntology | None:
        """Return the already-loaded ontology backed by ``path``, if any."""
        for lo in self._by_source.values():
            if lo.path == path:
                return lo
        return None

    def _refresh_file(self, path: Path, seen: set[str]) -> None:
        """Load/refresh a single ontology file and record its source in ``seen``."""
        mtime = path.stat().st_mtime
        existing = self._loaded_for_path(path)
        if existing and existing.mtime == mtime:
            seen.add(existing.spec.source)
            return

        spec = self._load_file(path)
        if (
            self._enabled_sources is not None
            and spec.source not in self._enabled_sources
        ):
            # Logged at debug only: reload() re-evaluates disabled files on every
            # call (they are never cached), so emitting this at INFO spams the log
            # and misleads. The one-time _log_enablement_summary() is the explicit
            # INFO-level record of what is enabled vs disabled.
            logger.debug(
                "Skipping disabled ontology source=%s (not in enabled_sources) from %s",
                spec.source,
                path.name,
            )
            return

        self._by_source[spec.source] = _LoadedOntology(spec, mtime, path)
        seen.add(spec.source)
        logger.info(
            "Loaded ontology source=%s version=%s dialect=%s from %s",
            spec.source,
            spec.version,
            spec.dialect.value,
            path.name,
        )

    def reload(self) -> None:
        """Scan the ontology directory; load new/changed files."""
        if not self._dir.exists():
            logger.warning("Ontology dir does not exist: %s", self._dir)
            return
        with self._lock:
            seen: set[str] = set()
            for path in sorted(self._dir.glob("*.y*ml")):
                try:
                    self._refresh_file(path, seen)
                except Exception as e:  # noqa: BLE001 - report and continue
                    logger.error("Failed to load ontology %s: %s", path, e)
            # Drop sources whose files disappeared.
            for src in list(self._by_source):
                if src not in seen:
                    logger.info("Removing ontology source no longer on disk: %s", src)
                    self._by_source.pop(src, None)

    @staticmethod
    def _normalize(source: str) -> str:
        """Fold common variants (case, separators) to a canonical key."""
        return source.strip().lower().replace("-", "_").replace(" ", "_")

    def resolve(self, source: str | None) -> str:
        """Map a (possibly loose or omitted) source to a registered source id.

        - None/empty -> the sole registered source when there is exactly one.
        - Case/separator-insensitive match (e.g. "ECM-DCM" -> "ecm_dcm").
        - A recognized sub-scope of a single source (e.g. "ecm"/"dcm" when only
          "ecm_dcm" exists) resolves to that source.
        Raises BQSError when it cannot be resolved unambiguously.
        """
        with self._lock:
            known = sorted(self._by_source)
        # Omitted source: default to the only one available.
        if source is None or not source.strip():
            if len(known) == 1:
                return known[0]
            raise BQSError(
                "Missing 'source'. Available sources: " + str(known),
                code="unknown_source",
            )
        if source in self._by_source:
            return source
        norm = self._normalize(source)
        by_norm = {self._normalize(s): s for s in known}
        if norm in by_norm:
            return by_norm[norm]
        # Sub-scope match: e.g. "ecm"/"dcm" are parts of the single "ecm_dcm".
        matches = [s for s in known if norm in self._normalize(s).split("_")]
        if len(matches) == 1:
            return matches[0]
        raise BQSError(
            f"Unknown data source '{source}'. Known sources: {known}",
            code="unknown_source",
        )

    def get(self, source: str | None) -> OntologySpec:
        """Return the ontology for a source, hot-reloading first.

        Accepts loose or omitted source values (see `resolve`). Raises BQSError
        with a clear message when the source cannot be resolved.
        """
        self.reload()
        canonical = self.resolve(source)
        with self._lock:
            return self._by_source[canonical].spec

    def list_sources(self) -> list[str]:
        self.reload()
        with self._lock:
            return sorted(self._by_source)
