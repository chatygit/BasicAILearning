# Asks to other teams — Capital Markets Agent

Each section stands alone and can be pasted into an email or ticket. Status
line = sent / answered; delete a section once it is done.

---

## 1. ADK / platform team — two token asks (status: drafted 2026-09-16, not sent)

### 1a. Gemini context caching for capital_markets_agent_v2
One banker question costs up to 584,182 prompt tokens across the session (ADK
trace 2026-09-16: 23 events, ~9 model calls). The static part of every call —
the loaded SKILL (~22k tokens), the agent instructions (~5k) and the
business-terms catalog fetched for the question (~12-16k) — is byte-identical
across those calls and re-sent each time. usageMetadata carries no
cachedContentTokenCount, so no context caching is in effect.

Ask: enable Gemini context caching (Vertex cached content) for the
capital_markets_agent_v2 sub-agent so the static prefix is cached once per
session (or per deployment for SKILL + instructions) and later calls pay only
the delta: (1) cache system instruction + loaded skill text; (2) if feasible,
cache the discover_business_terms result once fetched.

Expected: roughly 60-75 % fewer prompt tokens per question and proportionally
lower per-call latency — additive to our own config compression.

Questions for the team: is cached content available on the Vertex path this
deployment uses (minimum cacheable prefix, TTL)? Where is it declared (agent
config vs model client) so it survives the sub-agent transfer? Will
cachedContentTokenCount then appear in usageMetadata so we can measure it?

### 1b. Strip the duplicated MCP tool-result content
Measured: every MCP tool result reaches the model twice — content[0].text is
the full JSON serialised as text, next to the identical structuredContent.
Confirmed by a fresh-session tranche question landing at 66,561 prompt tokens
against a 67k prediction for duplication (51k without). It is ~25 % of every
call and doubles the business-terms catalog (16k → 32k for tranche). The
server-side fix (return one form) rides our release train; the faster path is
an ADK callback on the sub-agent:

```python
# before_model_callback — drop the text twin when structured content exists
def strip_duplicate_mcp_content(callback_context, llm_request):
    for content in llm_request.contents:
        for part in getattr(content, "parts", []) or []:
            fr = getattr(part, "function_response", None)
            if not fr or not isinstance(fr.response, dict):
                continue
            resp = fr.response
            if resp.get("structuredContent") and resp.get("content"):
                resp["content"] = []          # keep structuredContent only
    return None                               # continue with the modified request
```
Ask: can this callback be registered on the sub-agent in the POC deployment,
and does ADK's MCP toolset expose the response dict in this shape there?
Expected: ~12-16k fewer tokens per catalog fetch and ~1.5k per query result,
on every call, with no change to what the model can see.

### 1c. Token telemetry
ADK already surfaces usageMetadata per invocation — log promptTokenCount per
turn as a metric and alarm on a budget (e.g. 100k).

---

## 2. DB team — DGSTREAM indexes + stats (status: simplified request written 2026-09-04, not confirmed created)

Context: our reporting views join/filter these tables on keys that have no
index today (verified against the live index census, UAT 2026-09-02);
measured query times of 30-400 s drop to seconds once they exist. Re-verify
per environment before creating (index sets differ QA/UAT/PROD); create in
QA/UAT first, PROD with the next release window.

```sql
CREATE INDEX IX_OB_ORDER_TRADE_ROOT_ID
  ON DGSTREAM.OB_ORDER_TRADE (ROOT_ID) ONLINE;
CREATE INDEX IX_OB_HEDGE_ORDER_ROOT_ID
  ON DGSTREAM.OB_HEDGE_ORDER (ROOT_ID) ONLINE;
CREATE INDEX IX_OB_HEDGE_TRADE_ROOT_ID
  ON DGSTREAM.OB_HEDGE_TRADE (ROOT_ID) ONLINE;
CREATE INDEX IX_OPUS_BASE_TXN_RP_TXN_ROLE_TS
  ON DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
     (TRANSACTION_ID, PARTY_ROLE, PUBLISHED_TS) ONLINE;
CREATE INDEX IX_OPUS_BASE_TXN_TXN_ID
  ON DGSTREAM.OPUS_BASE_TRANSACTION (TRANSACTION_ID) ONLINE;
CREATE INDEX IX_OB_DEAL_TRANCHE_DEAL_TRANCHE
  ON DGSTREAM.OB_DEAL_TRANCHE (DEAL_ID, TRANCHE_ID) ONLINE;
-- optional, low priority
CREATE INDEX IX_OB_DEAL_ISSUER_GFCID
  ON DGSTREAM.OB_DEAL_ISSUER (GFCID) ONLINE;
```

| Table (rows, UAT) | Why |
|---|---|
| OB_ORDER_TRADE (490k) | deal-scoped trade queries filter ROOT_ID — full scan today |
| OB_HEDGE_ORDER (389k) | same pattern, hedge book |
| OB_HEDGE_TRADE (169k) | same pattern |
| OPUS_BASE_TRANSACTION_RELATED_PARTIES (361k) | joined by six view branches on TRANSACTION_ID + PARTY_ROLE — no index at all today |
| OPUS_BASE_TRANSACTION (140k) | joined on TRANSACTION_ID; key only trails an unrelated composite |
| OB_DEAL_TRANCHE (74k) | joined on (DEAL_ID, TRANCHE_ID); existing indexes lead with a different concatenated key |

Stats are stale on the two biggest tables (OB_ORDER 5.0M rows analysed
24-JUL; OB_ORDER_SIZE 4.8M rows analysed 14-APR):
```sql
EXEC DBMS_STATS.GATHER_TABLE_STATS('DGSTREAM','OB_ORDER',      cascade=>TRUE);
EXEC DBMS_STATS.GATHER_TABLE_STATS('DGSTREAM','OB_ORDER_SIZE', cascade=>TRUE);
```
A recurring stats job on the DGSTREAM OB_/OPUS_ tables would be welcome.
Verification: our deal-scoped trade/hedge probes go from full-scan seconds to
index-probe milliseconds; no application change on your side.

---

## 3. BDS / Starburst team — Oracle NUMBER mapping on bds_dg_oraas (status: drafted 2026-09-03; OPTIONAL since UAT 2026-09-17 — Trino SHOW COLUMNS now maps every cast metric as decimal(38,4)/(38,6); keep only as a safety net for unconstrained columns)

Ask: on catalog bds_dg_oraas set
```
oracle.number.default-scale = 9
oracle.number.rounding-mode = HALF_UP
```
Why: view columns defined as expressions (NVL/SUM/ROUND/CASE) publish as
unconstrained NUMBER (null precision/scale); with the current scale-0 mapping
whole numbers read fine but fractional values raise JDBC "Rounding necessary"
(1,051 of 35,034 rows in the failing query, 2026-09-03). Rounding-mode ALONE
is not acceptable — it would silently truncate fees (0.0125 → 0). Our views
now CAST every metric column to NUMBER(38,x) (Option 2), so this property
matters only for columns we have not cast; it remains the safety net.

Lossless argument: amounts are ROUND(…,4) and fees ROUND(…,6) at source, so
every value fits DECIMAL(38,9) exactly. Catalog-wide effect to review: every
unconstrained NUMBER shifts decimal(38,0) → decimal(38,9), max integer digits
38 → 29 (our largest observed values are ~14 digits). If the connector exposes
number_default_scale as a catalog SESSION property, tell us — the MCP server
could set it per session instead.

PROD: request the same two properties on the PROD catalog at promote time,
and PROD must run the ROUND-bounded view release first; the counts above are
DEV/UAT measurements, never PROD facts.
Verification: `DESCRIBE bds_dg_oraas.dgstream.vw_order_detail` shows
order_amount as decimal(38,9).

Metadata-cache question of 2026-09-16 WITHDRAWN 2026-09-17: the "column cannot
be resolved" error was a partial view deploy, not the connector cache. db-asks
S3 stays our detector after every deploy.

---

## 4. PO / MRM coordination (status: to say before the next push)
- The PO holds the DCM UAT results (85 %, minimum 80 %) until our push lands;
  a mid-cycle change invalidates the sample — agree the push date first.
- Citi solo deal in the PO's restructured prompt priced 18-Sep-2026, not
  14-Sep (14-Sep is the deal id's creation date).
- BlueFin does not exist in QA; the TC2 retest must run on UAT.

---

## 5. Data owners / governance — a PROD-shaped UAT (status: not yet asked formally)
We test against a UAT copy where test deals carry real issuer names over
synthetic books (51 % of DCM and 86 % of ECM deals have no orderbook; the 15
largest "IPOs" are nameless 100bn shells). Every coverage number in the
agent's doctrine is therefore a UAT number, and PROD defects (the "Limit
returned as Demand" ticket) reach us only as tickets.
Ask, in order of preference:
1. A masked PROD snapshot into UAT: last 24 months of deals, tranches and
   orders; investor and salesperson names hashed or replaced from a lookup;
   deal/issuer names kept (public information); amounts kept.
2. If (1) is refused: run the count-only census pack
   (`views/_checks/db-asks.sql` S4) on PROD at each release and return the
   screenshots — no rows leave PROD.
3. Read access to PROD OCP query logs and ADK traces (behaviour, not data).
