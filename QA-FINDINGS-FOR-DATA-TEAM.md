# Findings on VW_DEAL_ORDER_SUMMARY — for QA to share with the data team

Two findings from reading the view definition, written up so QA can pass them
on. We do not own the view and are not proposing wording for the fix — the
owning team decides whether and how to change it. Our side compensates in the
agent config either way (noted under each finding).

---

## Ask 1 (correctness, small): make ECM `DEAL_SHARING_TYPE` mean what DCM's means

The two branches define the same column differently.

**DCM — correct.** SOLO requires exactly one dealer, and that it is Citi:
```sql
CASE WHEN MIN(S.DEALER) = MAX(S.DEALER)
      AND MIN(S.DEALER) LIKE '%Citigroup Global%'
     THEN 'SOLO' ELSE 'SHARED' END
```

**ECM — flags SOLO on any Citi lead role, regardless of syndicate size:**
```sql
CASE WHEN COUNT(CASE WHEN SYNDICATE_ROLE IN ('Sole Bookrunner','Lead Manager/Bookrunner',
                                             'Global Coordinator and Bookrunner','Global Coordinator')
                      AND SYNDICATE_MEMBER_NAME LIKE '%Citigroup Global%' THEN 1 END) > 0
     THEN 'SOLO' ELSE 'SHARED' END
```
A ten-bank ECM syndicate with Citi as *joint* bookrunner is labelled `SOLO`.

**Impact:** any "Citi solo deals" question over-counts on ECM. We believe this
is behind QA finding #13 (156 solo deals, visibly inflated).

**If it is changed, the value domain should stay exactly `SOLO` / `SHARED`** (no
new values — downstream consumers depend on the two). The ECM predicate would
need to require a single syndicate member, as DCM already does:
```sql
CASE WHEN COUNT(DISTINCT SYNDICATE_MEMBER_NAME) = 1
      AND MAX(SYNDICATE_MEMBER_NAME) LIKE '%Citigroup Global%'
     THEN 'SOLO' ELSE 'SHARED' END
```
If the current ECM behaviour is intentional and means "Citi-led", please tell us
— we will treat it as such and stop calling it solo. Either answer unblocks us;
the ambiguity is the problem.

*Evidence to attach:* section D of `entity-search-diagnostics.sql` counts how
many `SOLO`-labelled ECM tranches actually have more than one member.

*Until this is resolved* the agent uses `REGEXP_COUNT(SYNDICATE_MEMBER_NAME,'|') = 0`
for sole-managed ECM asks and states which reading it used.

---

## Ask 2 (performance): a purpose-built entity-search object

**The problem.** Every "which investor/issuer/deal do you mean?" lookup pays the
full cost of the view. From the DDL, one query materialises:

1. a `UNION ALL` of two branches, **each `SELECT DISTINCT` over ~50 columns**
   (including 4000-char LISTAGG strings — the dedupe alone is a full sort);
2. **four LISTAGG group-by subqueries** (syndicate members/roles/broker codes/
   B&D, identifiers, DCM identifiers, deal-sharing);
3. a **correlated LISTAGG scalar subquery per row** for `ISSUER_RATINGS`;
4. joins on **concatenated keys** (`DEAL_ID || '-' || TRANCHE_ID`) and one on
   `TO_CHAR(...)`, neither of which can use ordinary indexes.

A bare `SELECT COUNT(*)` on the view does not return in 3.3 s, which sets the
floor for every user question. Name lookups add `UPPER(name) LIKE '%stem%'`
(unsargable by construction) on top.

**What entity search actually needs** — none of the expensive parts:

| Field | Purpose |
|---|---|
| name + id (INVESTOR_NAME/GPNUM, ISSUER_NAME/GFCID, DEAL_NAME/DEAL_ID) | match and return |
| PRODUCT | entitlement scoping |
| deal count, last active date | rank candidates by activity |
| category / region / sector / ticker | disambiguation hints shown to the user |

**Possible direction (the team's call):** a small object over that shortlist — a materialised
view refreshed on your normal cadence would be ideal (entity lists tolerate
staleness of hours). Rows would be in the thousands, not millions, and name
lookups become sub-second.

**Cheaper alternative:** function-based indexes on
`UPPER(<name>)` for the name columns — these help prefix searches (`BLACK%`)
though not `%BLACK%`.

*Evidence to attach:* section C of `entity-search-diagnostics.sql` — the same
answer computed against the view vs. against the underlying tables. The gap is
the size of the prize.
