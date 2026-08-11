"""Domain query service — orchestrates the full BQS pipeline.

    validate request -> resolve ontology -> plan -> build SQL ->
    read-only validate -> execute -> format.

Exposes two entrypoints used by the MCP tools: discovery and query.
"""

from __future__ import annotations

import logging
import os
import re
import time

from pydantic import ValidationError

from bqs.dialects.factory import get_dialect
from bqs.executor import execute, fetch_as_of_date
from bqs.formatter import format_result
from bqs.models import BQSError, BQSRequest
from bqs.ontology import OntologyRegistry
from bqs.planner import plan_query
from bqs.sql_builder import build_sql
from bqs.sql_validator import assert_read_only
from config import settings

logger = logging.getLogger(__name__)

# NOTE: this is the *revenue returns* use case, NOT ours. Only a
# source literally named "revenue_returns_entities" is served from zen_api.
# `capital_markets_entity` therefore goes down the normal SQL path against
# VW_ENTITY_SEARCH — which is exactly the design intent ("SQL-backed
# replacement for the old zen-API entity path FOR ECM/DCM").
ENTITY_SOURCE = "revenue_returns_entities"

_DEFAULT_ONTOLOGY_DIR = os.path.join(
    os.path.dirname(__file__), "..", "bqs", "ontology"
)


class DomainQueryService:
    def __init__(self, ontology_dir: str | None = None) -> None:
        ont_dir = ontology_dir or os.getenv("BQS_ONTOLOGY_DIR") or _DEFAULT_ONTOLOGY_DIR
        # Restrict the server to a fixed set of use cases. Defaults to the
        # ECM/DCM (Trino) source only, so the agent cannot query any other DB.
        # Override with a comma-separated BQS_ENABLED_SOURCES env var; set it to
        # empty/"*" to allow every ontology found on disk.
        #
        # ---------------------------------------------------------------------
        # DEPLOYMENT LANDMINE. This allow-list is an EXACT match on
        # each ontology's `source`. The four-view migration renamed the single
        # `capital_markets` source into FOUR: capital_markets_deal / _tranche / _order / _entity.
        # If BQS_ENABLED_SOURCES (or settings.bqs_enabled_sources) still says
        # "capital_markets", ALL FOUR objects are loaded and then silently ignored, and
        # discovery returns nothing. Set it to the four names, or to "*".
        # This is a promote-checklist item, not a code change.
        # ---------------------------------------------------------------------
        raw = os.getenv("BQS_ENABLED_SOURCES") or settings.bqs_enabled_sources
        enabled: set[str] | None
        if raw.strip() in ("", "*"):
            enabled = None
        else:
            enabled = {s.strip() for s in raw.split(",") if s.strip()}
        self.registry = OntologyRegistry(ont_dir, enabled_sources=enabled)

    # -- discovery ------------------------------------------------------------
    def discover(self, source: str | None = None) -> dict:
        """Return the governed catalog of business names (no schema)."""
        if source:
            spec = self.registry.get(source)
            return {"error": False, "sources": [spec.discovery()]}
        catalogs = [
            self.registry.get(s).discovery() for s in self.registry.list_sources()
        ]
        # NOTE: the no-argument path returns ALL catalogs — and because
        # registry.get() reloads, it also re-scans the ontology directory once
        # per source. Passing `source` is both smaller and cheaper.
        return {"error": False, "sources": catalogs}

    # -- query ----------------------------------------------------------------
    @staticmethod
    def _validation_error(e: ValidationError) -> dict:
        """Turn pydantic's noisy error into a short, corrective message the
        agent can act on, naming the offending field(s) only."""
        problems = []
        for err in e.errors():
            loc = ".".join(str(p) for p in err.get("loc", ())) or "(body)"
            problems.append(f"{loc}: {err.get('msg', 'invalid')}")
        msg = (
            "Invalid request shape. Fix the field(s) below and retry. "
            "Required: 'metric' (string). 'source' is optional (defaults to "
            "the single configured source). "
            # NOTE: that parenthetical is misleading in a four-source
            # deployment — `resolve()` only defaults when EXACTLY ONE source is
            # registered; with four it raises "Missing 'source'". Consider:
            # "'source' is required whenever discovery returns more than one
            # source."
            "'dimensions'/'order' are lists; each filter is "
            "{\"field\", \"op\", \"value\"}. Problems: " + "; ".join(problems)
        )
        logger.warning("BQS request validation failed: %s", problems)
        return BQSError(msg, code="invalid_request").to_dict()

    _FIELD_MISS_CODES = ("unknown_filter", "unknown_dimension", "unknown_metric")

    def _explain_cross_object(self, err: BQSError, request: dict) -> dict:
        """Say WHERE a missing field actually lives, or that it exists nowhere.

        A BQS request runs against ONE object, and the four objects are at
        different grains — so a question like "top investors by allocation in
        ENERGY deals" is not expressible: allocation and investor_category are
        on capital_markets_order, `sector` only on capital_markets_deal. Told merely "unknown
        filter 'sector', known filters: [...]", the agent guessed, failed,
        guessed again — ten run_bqs_query calls and a 429 RESOURCE_EXHAUSTED.

        The registry knows every object's fields, so the error can distinguish
        the two cases the agent cannot: a field that exists at ANOTHER grain
        (say so, and that one request cannot span them) versus one that exists
        nowhere (say the data does not support it, and stop).
        """
        payload = err.to_dict()
        try:
            if err.code not in self._FIELD_MISS_CODES:
                return payload
            match = re.search(r"'([^']+)'", err.message or "")
            if not match:
                return payload
            field = match.group(1)
            here = str(request.get("source") or "").strip()
            elsewhere = []
            for name in self.registry.list_sources():
                if name == here:
                    continue
                spec = self.registry.get(name)
                if field in spec.filters or field in spec.dimensions:
                    elsewhere.append(name)
            if elsewhere:
                payload["message"] = (
                    f"{err.message} "
                    f"'{field}' DOES exist on {', '.join(elsewhere)} — a different "
                    f"grain. One request runs against ONE object and cannot span "
                    f"them, so this question cannot be answered as asked. Do NOT "
                    f"retry with a guessed field name. Either drop '{field}' and "
                    f"answer what this object supports, or answer at the other "
                    f"object's grain — then tell the user plainly which one you "
                    f"did and what it leaves out."
                )
                payload["field_available_on"] = elsewhere
            else:
                payload["message"] = (
                    f"{err.message} '{field}' is not available on ANY object, so "
                    f"the data does not support this question. Do NOT retry with "
                    f"another guess — say plainly that this attribute is not "
                    f"tracked and offer what the listed fields can answer."
                )
                payload["field_available_on"] = []
            logger.info(
                "BQS field miss: field=%s source=%s available_on=%s",
                field, here or "<unset>", elsewhere,
            )
        except Exception as exc:  # noqa: BLE001 - never break an error path
            logger.debug("cross-object explanation skipped: %s", exc)
        return payload

    @staticmethod
    def _enrich_result(result: dict, req, spec, dialect, row_count: int, plan=None) -> None:
        """Attach best-effort suggestions/disambiguation to ``result`` in place.

        Enrichment must never break the response, so all failures are swallowed.
        """
        try:
            if row_count == 0:
                # Nothing matched: the agent likely guessed a value that isn't
                # spelled/cased like the real data. Attach fuzzy "did_you_mean"
                # suggestions so it can self-correct without a new tool.
                from bqs.suggestions import build_suggestions

                sugg = build_suggestions(req, spec, dialect)
                if sugg:
                    result["suggestions"] = sugg
            else:
                # Non-zero result: if an entity-name filter over-matched (blended
                # multiple distinct issuers/investors/deals), attach a
                # disambiguation block so the agent can isolate one entity.
                from bqs.suggestions import build_disambiguation

                disambig = build_disambiguation(
                    req, spec, dialect, result_rows=result.get("rows"), plan=plan
                )
                if disambig:
                    result["disambiguation"] = disambig
        except Exception as e:  # noqa: BLE001 - enrichment never breaks the response
            logger.warning("Result enrichment failed: %s", e)
        # NOTE: this is the authoritative statement of the suggestion
        # contract — `suggestions` fire ONLY on row_count == 0, `disambiguation`
        # ONLY on a non-empty result. So a filter that returns the WRONG rows
        # (e.g. sector 'Energy' missing 'Oil & Gas') gets no help at all. That
        # split drives SKILL §7b.

    def run(self, request: dict) -> dict:
        try:
            req = BQSRequest.model_validate(request)
        except ValidationError as e:
            return self._validation_error(e)
        try:
            spec = self.registry.get(req.source)
            # Use the canonical source id downstream (req.source may be a loose
            # alias like "ecm"/"ECM-DCM" that resolved to "capital_markets").
            resolved_source = spec.source

            # revenue_returns_entities ALWAYS resolves via zen_api (zen-client
            # search + zen-coverage revenue-access filter). No SQL, no fallback.
            if resolved_source == ENTITY_SOURCE:
                return self._run_zen_entity(req, resolved_source)

            # Phase timers. A single run_bqs_query call is one agent hop, and a
            # hop is the unit users feel — so the split between "we built it",
            # "the warehouse ran it" and "we enriched it" is what any latency
            # work has to be argued from. Wall-clock only; no extra work done.
            t0 = time.perf_counter()
            plan = plan_query(req, spec)
            dialect = get_dialect(spec.dialect)
            built = build_sql(plan, dialect)
            assert_read_only(built.sql)
            t_build = time.perf_counter()
            logger.info(
                "BQS accepted source=%s metric=%s sql=%s",
                resolved_source,
                req.metric,
                built.sql,
            )
            columns, rows = execute(spec, built, dialect)
            t_exec = time.perf_counter()
            result = format_result(
                columns,
                rows,
                source=resolved_source,
                metric=req.metric,
                sql_audit=built.sql,
                row_count=len(rows),
                as_of_date=fetch_as_of_date(spec, dialect),
                offset=plan.offset,
                limit=plan.limit,
            )
            t_format = time.perf_counter()
            # NOTE: `sql_audit` puts the generated SQL INTO the response the
            # agent sees. The skill's confidentiality rule ("never disclose the
            # generated SQL") is therefore a real, load-bearing instruction —
            # the SQL is right there in the payload, not merely conceptual.
            self._enrich_result(result, req, spec, dialect, len(rows), plan)
            t_enrich = time.perf_counter()
            # enrich is NOT free: build_suggestions runs a DISTINCT probe per
            # suggestable filter on 0 rows, and build_disambiguation runs one
            # bounded DISTINCT probe whenever an entity-name filter's field was
            # not projected as a dimension. Both are serial, after the answer is
            # already in hand — so a large `enrich` here means an extra
            # round-trip the agent could have avoided by projecting that field.
            logger.info(
                "BQS timing source=%s metric=%s rows=%d | build=%.2fs "
                "execute=%.2fs format=%.2fs enrich=%.2fs total=%.2fs",
                resolved_source,
                req.metric,
                len(rows),
                t_build - t0,
                t_exec - t_build,
                t_format - t_exec,
                t_enrich - t_format,
                t_enrich - t0,
            )
            return result
        except BQSError as e:
            logger.warning("BQS rejected: %s", e.message)
            return self._explain_cross_object(e, request)
        except Exception as e:  # noqa: BLE001
            # Never leak a raw stack/driver string to the agent — give a stable,
            # non-actionable message so it doesn't loop on the same request.
            logger.error("Unexpected BQS failure: %s", e)
            return BQSError(
                "An unexpected server error occurred while running the query. "
                "This is not a problem with your request wording — do not retry "
                "the same query repeatedly.",
                code="internal_error",
            ).to_dict()

    # -- zen_api entity resolution --------------------------------------------
    @staticmethod
    def _extract_entity_args(req: BQSRequest) -> tuple[str, str]:
        """Pull the search term from the BQS filters.

        A ``gfcid`` eq filter takes priority; otherwise the ``gfcid_name``
        like/eq value is used (surrounding % wildcards stripped).
        """
        entity_name = ""
        gfcid = ""
        for f in req.filters:
            val = f.value
            if isinstance(val, (list, tuple)):
                val = val[0] if val else ""
            val = str(val or "").strip()
            if f.field == "gfcid" and f.op.value == "eq" and val:
                gfcid = val
            elif f.field == "gfcid_name" and f.op.value in ("like", "eq") and val:
                entity_name = val.strip("%").strip()
        return entity_name, gfcid

    def _run_zen_entity(self, req: BQSRequest, source: str) -> dict:
        """Serve revenue_returns_entities from zen_api (no SQL executed)."""
        from bqs.entity.zen_entity_search import zen_entity_search
        from middleware.soeid_middleware import get_soeid

        entity_name, gfcid = self._extract_entity_args(req)
        soeid = get_soeid()

        try:
            clients = zen_entity_search(
                entity_name=entity_name, gfcid=gfcid, soeid=soeid
            )
        except ValueError as e:
            # URLs / config missing.
            raise BQSError(str(e), code="config_error") from e
        except Exception as e:  # noqa: BLE001 - zen HTTP / upstream failure
            logger.error("zen entity search failed: %s", e)
            raise BQSError(
                "The client entitlement service is temporarily unavailable. "
                "Do not retry the same query repeatedly.",
                code="service_unavailable",
            ) from e

        columns = [
            "gfcid",
            "gfcid_name",
            "client_level",
            "cb_priority",
            "ib_priority",
            "managed_country_name",
            "super_industry",
        ]
        rows: list[tuple] = []
        seen: set[str] = set()
        for c in clients:
            g = c.get("gfcId") or c.get("GFCID") or ""
            name = c.get("clientName") or c.get("COMPANY_NAME") or c.get("GFCID_NAME") or ""
            level = c.get("clientLevel") or c.get("CLIENT_LEVEL") or ""
            cb = c.get("cbPriority") or c.get("cbpriority") or ""
            ib = c.get("ibPriority") or c.get("ibpriority") or ""
            country = c.get("managedCountryName") or c.get("managecountryname") or ""
            industry = c.get("superIndustry") or c.get("superindustry") or ""
            key = str(g)
            if key in seen:
                continue
            seen.add(key)
            rows.append((g, name, level, cb, ib, country, industry))

        result = format_result(
            columns,
            rows,
            source=source,
            metric=req.metric,
            sql_audit="zen_api entity search (no SQL executed)",
            row_count=len(rows),
        )

        # Disambiguation built directly from the zen rows (no DB probe). Trigger
        # on >1 distinct GFCID (not name — two clients can share a name) and carry
        # the full attribute set so the agent can render the whole table.
        if len({str(r[0]) for r in rows if r[0]}) > 1:
            result["disambiguation"] = [
                {
                    "field": "gfcid_name",
                    "your_value": entity_name,
                    "matched_clients": [
                        {
                            "gfcid": r[0],
                            "gfcid_name": r[1],
                            "client_level": r[2],
                            "cb_priority": r[3],
                            "ib_priority": r[4],
                            "managed_country_name": r[5],
                            "super_industry": r[6],
                        }
                        for r in rows
                    ],
                    "hint": (
                        "Your filter on 'gfcid_name' matched multiple distinct "
                        "entitled clients. Ask the user to pick ONE by number, "
                        "then re-run scoped to that single GFCID."
                    ),
                }
            ]
        return result


# Module-level singleton for the MCP tools.
_service: DomainQueryService | None = None


def get_service() -> DomainQueryService:
    global _service
    if _service is None:
        _service = DomainQueryService()
    return _service
