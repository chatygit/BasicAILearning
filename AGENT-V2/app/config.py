"""Lightweight settings shim for the BQS governed-SQL subsystem.

The capital-markets (ECM/DCM) BQS engine copied from the text-to-sql starter
kit expects a module-level ``settings`` object exposing a handful of
BQS-related attributes. This repo configures itself from environment variables
rather than pydantic-settings, so this shim provides the same attribute surface
backed by ``os.getenv`` with sensible defaults.

Only the fields actually referenced by the copied engine are provided:
  * ``bqs_enabled_sources`` - comma-separated allow-list of ontology source ids
    the server may serve. Defaults to the ECM/DCM (Trino) use case only.
  * ``bqs_oracle_cyberark_fid`` / ``bqs_db_user`` / ``bqs_db_password`` - only
    used by the Oracle/Postgres execution path (unused for the Trino-backed
    capital_markets source, but kept so imports resolve).
"""

from __future__ import annotations

import os


class _Settings:
    @property
    def bqs_enabled_sources(self) -> str:
        # Restrict the server to the four grain-aligned Capital Markets objects
        # (deal / tranche / order / entity). The legacy single-view v1 source
        # ("ecm_dcm") has been removed. Override with a comma-separated
        # BQS_ENABLED_SOURCES env var (or "*" to serve every ontology on disk).
        #
        # MIGRATION SHIM (2026-08-10, ecm_dcm -> capital_markets rename): a
        # deployment chart that still lists the OLD source ids would otherwise
        # match nothing — every object loads and is then silently ignored, and
        # discovery returns an empty set with no error. Rewrite legacy ids here
        # so the rename does not have to be deploy-ordered. Remove once every
        # environment has been updated.
        raw = os.getenv(
            "BQS_ENABLED_SOURCES",
            "capital_markets_deal,capital_markets_tranche,"
            "capital_markets_order,capital_markets_entity",
        )
        return ",".join(
            part.strip().replace("ecm_dcm_", "capital_markets_")
            for part in raw.split(",")
        )

    @property
    def bqs_ontology_dir(self) -> str | None:
        return os.getenv("BQS_ONTOLOGY_DIR")

    @property
    def bqs_oracle_cyberark_fid(self) -> str | None:
        return os.getenv("BQS_ORACLE_CYBERARK_FID")

    @property
    def bqs_db_user(self) -> str | None:
        return os.getenv("BQS_DB_USER")

    @property
    def bqs_db_password(self) -> str | None:
        return os.getenv("BQS_DB_PASSWORD")


settings = _Settings()

# NOTE: the in-code default already lists the four post-split source ids, so a
# fresh deployment serves all four objects correctly. The remaining risk is an
# ENVIRONMENT override left over from v1: if BQS_ENABLED_SOURCES is set to
# "capital_markets" anywhere in the deployment config, it wins over this default and
# every object is loaded and then silently ignored. Verify the var is unset (or
# lists the four names) rather than assuming the default applies.
