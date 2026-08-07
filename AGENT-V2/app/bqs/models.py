"""Canonical BQS (Business Query Specification) JSON contract.

This is the ONLY structure the agent is allowed to submit. It speaks purely
in business-friendly names — never real table/column names. The server maps
these names to physical schema privately via the ontology.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class FilterOperator(str, Enum):
    """Operators the agent may request. Each maps to a safe SQL fragment."""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"
    LIKE = "like"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    # NOTE: there is deliberately NO not_like. Negation of broker/syndicate/B&D
    # logic goes through a computed_filter with negate=True, which is NULL-safe
    # (see sql_builder._build_where).


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class BQSFilter(BaseModel):
    """A single filter expressed in business names."""

    field: str = Field(..., description="Business dimension/filter name.")
    op: FilterOperator = Field(..., description="Comparison operator.")
    value: Any = Field(
        default=None,
        description="Filter value. List for in/not_in; 2-item list for between; "
        "omitted for is_null/is_not_null.",
    )

    @field_validator("field")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("filter.field must be a non-empty business name")
        return v


class BQSOrder(BaseModel):
    field: str = Field(..., description="Business metric or dimension name.")
    direction: SortDirection = SortDirection.ASC


class BQSHaving(BaseModel):
    """A post-aggregation threshold on a metric (SQL HAVING).

    Lets the agent express group-count / group-sum thresholds — e.g. investors
    who participated in more than 5 deals (metric 'deal_count' gt 5), or
    multi-currency deals (metric 'currency_count' gt 1). Only comparison
    operators are allowed; the metric is any metric name from discovery.
    """

    metric: str = Field(..., description="Metric name to threshold (from discovery).")
    op: FilterOperator = Field(..., description="Comparison operator (eq/ne/gt/gte/lt/lte).")
    value: Any = Field(..., description="Threshold value (number).")

    @field_validator("metric")
    @classmethod
    def _strip_metric(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("having.metric must be a non-empty metric name")
        return v


class BQSComputedFilter(BaseModel):
    """A governed computed filter reference (e.g. broker anchoring).

    The agent supplies only the computed-filter name and, when required, a
    business token (e.g. "citi"). The server owns the SQL/regex entirely.
    """

    name: str = Field(..., description="Computed filter name from discovery.")
    token: Optional[str] = Field(
        default=None,
        description="Business token (e.g. 'citi'). Omit for token-less filters.",
    )
    negate: bool = Field(
        default=False,
        description="When true, match rows that do NOT satisfy the filter — "
        "e.g. 'non-B&D' (bill_and_deliver, negate) or 'not Citi' "
        "(syndicate_member 'citi', negate).",
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("computed_filter.name must be a non-empty name")
        return v


class BQSRequest(BaseModel):
    """The canonical governed request contract.

    The agent fills this out using ONLY names it discovered through the
    discovery tool — never invented from memory.
    """

    source: Optional[str] = Field(
        default=None,
        description="Business data source (ontology) name. Optional — omit to "
        "use the single configured source; loose aliases (e.g. 'ecm') are "
        "resolved server-side.",
    )
    metric: str = Field(..., description="Business metric name to aggregate.")
    dimensions: list[str] = Field(
        default_factory=list,
        description="Business dimension names to group by.",
    )
    filters: list[BQSFilter] = Field(default_factory=list)
    computed_filters: list[BQSComputedFilter] = Field(
        default_factory=list,
        description="Governed computed filters (e.g. broker anchoring).",
    )
    derived_filters: list[str] = Field(
        default_factory=list,
        description="Governed derived-predicate names from discovery (e.g. "
        "'settlement_currency_mismatch'). Token-less; the server owns the SQL.",
    )
    having: list[BQSHaving] = Field(
        default_factory=list,
        description="Post-aggregation metric thresholds (SQL HAVING), e.g. "
        "deal_count gt 5. Comparison operators only.",
    )
    time_grain: Optional[str] = Field(
        default=None,
        description="Optional time bucket (e.g. day, week, month, quarter, year).",
    )
    time_dimension: Optional[str] = Field(
        default=None,
        description="Date dimension to bucket when time_grain is set. Defaults "
        "to the source's default_time_dimension when omitted.",
    )
    order: list[BQSOrder] = Field(default_factory=list)
    limit: Optional[int] = Field(
        default=None, ge=1, description="Max rows to return."
    )

    @field_validator("source")
    @classmethod
    def _strip_source(cls, v: str | None) -> str | None:
        # Optional: normalize to None when blank so the server can default it.
        v = (v or "").strip()
        return v or None

    @field_validator("metric")
    @classmethod
    def _strip_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("metric is a required business name")
        return v


class BQSError(Exception):
    """Raised when a BQS request cannot be satisfied.

    Carries a clear, agent-facing message. Unknown names produce this instead
    of the system guessing what was meant.
    """

    def __init__(self, message: str, *, code: str = "bqs_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"error": True, "code": self.code, "message": self.message}
