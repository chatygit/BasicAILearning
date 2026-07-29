# Capital Markets Text2SQL Agent — V1 Scope Contract

**Purpose:** the testable definition of what the agent supports at V1 go-live (July 31).
QA verdicts are valid against this contract on an environment running the promoted
configs + deployed MCP server, after app restart. Findings from stale environments
are environment findings, not agent defects.

## 1. Supported ask classes (the QA prompt sheet maps onto these)

1. **Deal listings & details** — by status, sector (ECM), size, offering type (ECM),
   equity/product type (ECM), use of proceeds, exchange (ECM), date windows, region.
2. **Tranche listings & details** — sizes (units per product), currencies, tenors (DCM),
   coupon (DCM), seniority/reg category/ESG (DCM), status (DCM), per-tranche identifiers.
3. **Security-identifier lookups** — CUSIP/ISIN/FIGI/RIC etc. as filter or projection;
   pinpoint semantics (a zero-row windowed id lookup retries without the window).
4. **Syndicate & brokers** — members per deal/tranche, roles (ECM), Citi/any-bank B&D,
   solo deals (DEAL_SHARING_TYPE), participation by bank.
5. **Orders & investors** — order listings (book-profile presentation for large books),
   OTT/order type (ECM), IOI type, meeting type (ECM), investor region/category (ECM),
   demand/allocation metrics, top investors (family-scoped by default), fill/coverage (ECM).
6. **Aggregations** — top-N, group-bys (by issuer/currency/sector/category/tranche),
   counts, derived metrics (§5a of the skill), breakdowns that reconcile to their totals.
7. **Conversation** — follow-ups reuse context; column-add keeps identical rows;
   paging via "next 20" with absolute row numbers; drill-down by id or row number.

## 2. Per-product column availability (asks outside this = expected redirect, not a bug)

- **ECM-only:** EQUITY_TYPE, PRODUCT_TYPE, SECTOR, OFFERING_TYPE, EXECUTION_STATUS,
  EXCHANGE, ORDER_TYPE (OTT is an ECM concept), INVESTOR_CATEGORY, MEETING_TYPE,
  SETTLEMENT_TS (settlement windows), DEAL_REGION.
- **DCM-only:** TRANCHE_STATUS, PRODUCT_CLASS, SENIORITY, REG_CATEGORY, ESG_BOND,
  COUPON_TYPE/FREQ, DELIVERY_TYPE, ISSUER_RATINGS, TENORS, SECURITIES_MATURITY.
- **Vocab differs per product:** DEAL_STATUS; USE_OF_PROCEEDS (DCM list is small).
- **Expected behavior on a cross-product ask** (e.g. "DCM deals by sector"): the agent
  explains the column is not tracked for that product and offers the equivalent.
  That message IS the pass criterion.

## 3. Response contract

1. Tables for data rows (business-term headers, `#` column with absolute row numbers,
   ids as drill-down handles); numbered lists only for choices.
2. Units always labeled: ECM quantities in shares, DCM amounts with currency; banker
   notation (USD 2.1bn / 3.0mm shares); dates as 25-Nov-2024; flags as words.
3. Display cap 20 rows + mandatory "Showing N of M" banner. **Large order books
   (100–2,000 orders) default to the BOOK PROFILE**: headline totals, top 10–15 orders
   by metric, one breakdown, tail summarized — then filter/aggregate/page doors.
4. Breakdowns must sum to their stated totals (or state the overlap).
5. No schema/SQL disclosure; no fabricated escalations; plain-language failures.

## 4. Expected refusals (by design — the redirect is the pass)

Matched orders · TTW · cancelled/deleted ORDERS (deal-level offered) · settlement-
currency mismatch is SUPPORTED (new column) · investor classification (category offered)
· selling restrictions · domicile/incorporation · hedge-securities count · peer graphs ·
greenshoe · pricing economics · export/download beyond UI capability · schema disclosure.
DCM structural limits: non-B&D syndicate composition and syndicate counts are not
determinable (single visible member = the B&D bank); coverage/fill ratios are ECM-only
(DCM demand = allocation by construction).

## 5. Out of scope V1 (best-effort, not guaranteed)

Cross-domain asks (fees/wallet → wallet agent; market data → market_data agent),
free-form analytics beyond §5a derived metrics, multi-deal comparisons requiring
self-joins, historical trend charting, data older than the view's population.

## 6. Known platform issues (tracked separately, not agent defects)

Tool-not-found on session start (born-without-tools registry issue) · type-twice /
no-response-second-time · chat-switch stuck "processing()" · stale-pod configs
(bootstrap-once requires app restart after promote) · UI download row cap (Vinit).
