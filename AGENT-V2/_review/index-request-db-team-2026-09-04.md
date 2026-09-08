# Index request — DGSTREAM (Capital Markets views workload)

Context in one line: our reporting views join/filter these tables on keys that
have no index today (verified against the live index census, 2026-09-02, UAT);
measured query times of 30-400s drop to seconds once these exist.

Please re-verify existence per environment before creating (index sets can
differ between QA/UAT/PROD), then create in QA/UAT first, PROD with the next
release window.

## 1. Create these four indexes

```sql
CREATE INDEX IX_OB_ORDER_TRADE_ROOT_ID
  ON DGSTREAM.OB_ORDER_TRADE (ROOT_ID) ONLINE;

CREATE INDEX IX_OB_HEDGE_ORDER_ROOT_ID
  ON DGSTREAM.OB_HEDGE_ORDER (ROOT_ID) ONLINE;

CREATE INDEX IX_OB_HEDGE_TRADE_ROOT_ID
  ON DGSTREAM.OB_HEDGE_TRADE (ROOT_ID) ONLINE;



CREATE INDEX IX_OB_DEAL_TRANCHE_DEAL_TRANCHE
  ON DGSTREAM.OB_DEAL_TRANCHE (DEAL_ID, TRANCHE_ID) ONLINE;
```

| Table (rows, UAT) | Why |
|---|---|
| OB_ORDER_TRADE (490k) | deal-scoped trade queries filter ROOT_ID — full scan today |
| OB_HEDGE_ORDER (389k) | same pattern, hedge book |
| OB_HEDGE_TRADE (169k) | same pattern |
| OB_DEAL_TRANCHE (74k) | joined on (DEAL_ID, TRANCHE_ID); existing indexes lead with a different concatenated key |

Optional, low priority:
```sql
CREATE INDEX IX_OB_DEAL_ISSUER_GFCID
  ON DGSTREAM.OB_DEAL_ISSUER (GFCID) ONLINE;
```

## 2. Refresh optimizer stats (stale)

```sql
EXEC DBMS_STATS.GATHER_TABLE_STATS('DGSTREAM','OB_ORDER',      cascade=>TRUE);
EXEC DBMS_STATS.GATHER_TABLE_STATS('DGSTREAM','OB_ORDER_SIZE', cascade=>TRUE);
```

OB_ORDER is 5.0M rows last analyzed 24-JUL; OB_ORDER_SIZE is 4.8M rows last
analyzed 14-APR — badly stale for the two biggest tables in the workload.
A recurring stats job on the DGSTREAM OB_/OPUS_ tables would be welcome.

## 3. Verification
After creation: our deal-scoped trade/hedge probes (we run them) should go
from full-scan seconds to index-probe milliseconds; no application change is
needed on your side — views pick the indexes up automatically.

(Full analysis, predicate inventory, and the census this diffed against:
AGENT-V2/_review/index-review-2026-09-02.md.)

(2026-09-04 revision: the two OPUS_BASE index items were withdrawn — those
tables are being removed from our views entirely.)
