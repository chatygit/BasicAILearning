# VW_DEAL_ORDER_SUMMARY — findings for the data team

From the Ask-Banking ECM/DCM agent team, via QA. The agent reads this view
exclusively; we do not own it and are not proposing DDL wording. Each finding
states what we measured, the structural cause visible in the view definition,
and the directions we believe are open — the owning team decides.

**Headline:** the same query costs **1.4 s against the ECM branch and 107.9 s
against the DCM branch** — a ~75× gap that is structural, not data volume.

---

## Measurements

Identical query shape, run in SQL Developer, one branch at a time:

```sql
SELECT COUNT(*) FROM (
  SELECT INVESTOR_NAME, GPNUM,
         COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT,
         MAX(PRICING_TS)         AS LAST_ACTIVE,
         MAX(INVESTOR_CATEGORY)  AS CATEGORY,
         MAX(INVESTOR_REGION)    AS REGION
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT IN (<branch>)
     AND ( UPPER(INVESTOR_NAME) LIKE '%BLACKROCK%'
        OR SOUNDEX(UPPER(INVESTOR_NAME)) = SOUNDEX('BLACKROCK') )
   GROUP BY INVESTOR_NAME, GPNUM
);
```

| Variant | Rows | Elapsed |
|---|---:|---:|
| `PRODUCT IN ('ECM')`, LIKE + SOUNDEX | 60 | 1.4 s |
| `PRODUCT IN ('DCM')`, LIKE + SOUNDEX | 1,189 | **107.9 s** |
| `PRODUCT IN ('ECM','DCM')`, LIKE only | 907 | **88.3 s** |
| `PRODUCT = 'ECM'`, LIKE only, full enrichment | 45 | 2.9 s |
| `PRODUCT = 'ECM'`, names only, no aggregates | 45 | 2.8 s |
| `PRODUCT = 'ECM'`, prefix match `'BLACKROCK%'` | 42 | 2.8 s |
| `PRODUCT = 'ECM'`, exact `IN` list of 2 names | 6 | 2.6 s |
| `PRODUCT = 'ECM'`, `GPNUM = '00000000'` (matches nothing) | 0 | **1.2 s** |

Two things stand out beyond the ECM/DCM gap:

**Query shape is irrelevant.** On ECM every variant costs ~2.8 s — full
enrichment, names-only, prefix instead of leading wildcard, even an exact
`IN` list matching just 6 rows. Selectivity does not change the cost, which is
the signature of a fixed materialisation cost rather than predicate evaluation.
We have therefore stopped trying to tune it from our side.

**But sargable predicates DO push down.** The last row is the same query shape
with `GPNUM = '00000000'` (matches nothing): **1.2 s**, less than half the
2.9 s of a name search. So the optimizer can push a seekable equality down into
the branch — it simply has nothing to seek on for `UPPER(<name>) LIKE …`. That
is the concrete argument for the function-based name indexes listed below: they
would let name lookups behave like the 1.2 s floor rather than a 2.9 s scan.

A bare `SELECT COUNT(*) FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY` did not return
within 3.3 s, so there is a floor cost on every query regardless of filters.

*Why this matters to the product:* this is the lookup behind "which investor did
you mean?" — it runs **before** the user's actual question, so on DCM it is the
dominant part of the agent's response time.

---

## Finding 1 — DCM branch: a correlated LISTAGG per row, inside `SELECT DISTINCT`

The DCM branch computes `ISSUER_RATINGS` as a correlated scalar subquery:

```sql
( SELECT LISTAGG(OTR.AGENCY || ' - ' || OTR.VALUE || '(' || OTR.OUTLOOK || ')', ', ')
             WITHIN GROUP (ORDER BY OTR.AGENCY)
    FROM DGSTREAM.OB_TRANCHE_RATING OTR
   WHERE OTR.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID ) AS ISSUER_RATINGS
```

Two compounding issues:

1. It is **correlated**, so it evaluates per row of the branch — unlike the
   other multi-value columns (identifiers, syndicate members), which are
   pre-aggregated `LEFT JOIN (… GROUP BY …)` subqueries in the same view.
2. Because the branch is `SELECT DISTINCT` over all ~50 columns, this column
   participates in the dedupe, so it **cannot be optimised away** even when the
   consumer never selects `ISSUER_RATINGS` — which is the case for every entity
   lookup the agent makes.

**Directions open to you:** pre-aggregate it as a
`LEFT JOIN (SELECT DEAL_TRANCHE_ID, LISTAGG(...) FROM OB_TRANCHE_RATING GROUP BY DEAL_TRANCHE_ID)`,
matching the pattern already used for identifiers in the same branch; and/or an
index on `OB_TRANCHE_RATING(DEAL_TRANCHE_ID)` — the concatenation sits on the
*outer* side of that predicate, so an ordinary index on the ratings table is
usable.

---

## Finding 2 — `SELECT DISTINCT` over ~50 columns, including 4000-char LISTAGG strings

Both branches are `SELECT DISTINCT`. Deduplicating on wide LISTAGG text forces a
full sort/hash-unique of the branch before a consumer's predicate can reduce it.

**Direction:** if the underlying grain is already unique (deal × tranche × order
× syndicate row), the `DISTINCT` may be removable, or narrowable to the columns
that genuinely duplicate.

---

## Finding 3 — join keys no index can serve

| Location | Predicate | Why it hurts |
|---|---|---|
| DCM, 4 places | `X.DEAL_TRANCHE_ID = ODT.DEAL_ID \|\| '-' \|\| ODT.TRANCHE_ID` | key built per row by concatenation; the ODT side can never be seeked |
| ECM | `TO_CHAR(TT.ECM_TRANSACTION_TRANCHE_ID) = O.TRANCHE_ID` | function on the column blocks index access — suggests a datatype mismatch (numeric vs varchar) between the two tables |

**Directions:** align the datatypes so `TO_CHAR` is unnecessary, and/or add
function-based indexes matching these expressions.

---

## Finding 4 — ECM `DEAL_SHARING_TYPE = 'SOLO'` means "Citi-led", not "sole-managed"

The two branches define the same column differently.

**DCM — requires exactly one dealer, and that it is Citi:**
```sql
CASE WHEN MIN(S.DEALER) = MAX(S.DEALER)
      AND MIN(S.DEALER) LIKE '%Citigroup Global%'
     THEN 'SOLO' ELSE 'SHARED' END
```

**ECM — flags SOLO on any Citi lead role, with no check on syndicate size:**
```sql
CASE WHEN COUNT(CASE WHEN SYNDICATE_ROLE IN ('Sole Bookrunner','Lead Manager/Bookrunner',
                                             'Global Coordinator and Bookrunner','Global Coordinator')
                      AND SYNDICATE_MEMBER_NAME LIKE '%Citigroup Global%' THEN 1 END) > 0
     THEN 'SOLO' ELSE 'SHARED' END
```

A ten-bank ECM syndicate with Citi as *joint* bookrunner is therefore labelled
`SOLO`.

**Measured: 25.1% of `SOLO`-labelled ECM tranches are not sole-managed.**

| ECM tranches where Citi holds a lead role | 9,617 |
|---|---:|
| …genuinely sole-managed (one syndicate member) | 7,207 |
| …**mislabelled `SOLO` (several members)** | **2,410 (25.1%)** |

Any "Citi solo" question over-reports by roughly a quarter on ECM. This is
almost certainly behind QA finding #13 (156 "Citi solo" deals, visibly
inflated).

**If it is changed, the value domain should stay exactly `SOLO` / `SHARED`** —
consumers depend on the two values. If the current ECM behaviour is intentional
and means "Citi-led", telling us that is equally useful: the ambiguity is the
problem, not either answer.

The query behind those numbers (runs in 0.3 s against the base table — worth
noting on its own: the underlying tables are fast, the cost is in the view):

```sql
SELECT COUNT(*)                                          AS citi_led_tranches,
       SUM(CASE WHEN member_count = 1 THEN 1 ELSE 0 END) AS truly_sole_managed,
       SUM(CASE WHEN member_count > 1 THEN 1 ELSE 0 END) AS mislabelled_solo
  FROM (
    SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID,
           COUNT(DISTINCT SYNDICATE_MEMBER_NAME) AS member_count,
           MAX(CASE WHEN SYNDICATE_ROLE IN ('Sole Bookrunner','Lead Manager/Bookrunner',
                                            'Global Coordinator and Bookrunner','Global Coordinator')
                     AND SYNDICATE_MEMBER_NAME LIKE '%Citigroup Global%'
                    THEN 1 ELSE 0 END) AS citi_led
      FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
     GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
  )
 WHERE citi_led = 1;
```

*Our side meanwhile:* the agent treats ECM `SOLO` as "Citi-led" and derives true
sole-managed from the syndicate member list, stating which reading it used.

---

## Index candidates

Please check these against what already exists — we could not read
`ALL_INDEXES` for all objects.

| Table | Column(s) | Serves |
|---|---|---|
| `OB_TRANCHE_RATING` | `DEAL_TRANCHE_ID` | the correlated `ISSUER_RATINGS` subquery (Finding 1) |
| `OB_TRANCHE` | `DEAL_TRANCHE_ID` | DCM identifier LISTAGG subquery |
| `OB_TRANCHE_SYNDICATE_MEMBER` | `DEAL_TRANCHE_ID` | DCM deal-sharing subquery |
| `OB_DEAL_ISSUER` | `DEAL_TRANCHE_ID` | issuer join |
| `OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE` | `ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID` | ECM syndicate + deal-sharing LISTAGG subqueries |
| `OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL_IDENTIFIER` | `ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID` | ECM identifier LISTAGG subquery |
| `OB_ECM_ORDER` | `UPPER(INVESTOR_NAME)` (function-based) | exact/prefix investor lookup |
| `OB_ORDER` | `UPPER(NAME)` (function-based) | exact/prefix investor lookup (DCM) |
| `OPUS_ECM_TRANSACTION` | `UPPER(ISSUER_NAME_FROM_SOURCE)`, `UPPER(SYNDICATE_DEAL_NAME)` (function-based) | issuer / deal-name lookup |

One caveat on the name indexes: a b-tree on `UPPER(name)` serves
`= 'BLACKROCK'` and `LIKE 'BLACKROCK%'`, but **not** `LIKE '%BLACKROCK%'` —
which is what a user typing a partial name produces. If contains-style search
matters, an Oracle Text (`CONTEXT`) index is the mechanism that supports it.

Also worth checking whether optimizer statistics are current on these tables:
stale stats alone can produce bad plans independently of indexing.

---

## Longer-term option: a purpose-built entity-search object

Name lookups need only a small slice of this view:

| Field | Purpose |
|---|---|
| name + id (`INVESTOR_NAME`/`GPNUM`, `ISSUER_NAME`/`GFCID`, `DEAL_NAME`/`DEAL_ID`) | match and return |
| `PRODUCT` | entitlement scoping |
| deal count, last active date | rank candidates by activity |
| category / region / sector / ticker | disambiguation hints shown to the user |

None of the expensive parts — ratings, identifiers, syndicate lists, the wide
`DISTINCT` — are needed for this. A materialised view over that shortlist,
refreshed on your normal cadence (entity lists tolerate staleness of hours),
would be a few thousand rows and would make these lookups sub-second on both
products.

---

## Reproducing

`entity-search-diagnostics.sql` (agent team) contains the measured queries
per-branch and per-lever, plus the Finding 4 quantification query above.
