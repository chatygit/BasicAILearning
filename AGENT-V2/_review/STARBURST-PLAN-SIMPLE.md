# Capital Markets Agent on Starburst — the simple version

*The short read for the team. The detailed plan (SQL port, layouts, caching) is
in `ICEBERG-PLAN.md`.*

## In one sentence

The data moves from Oracle into three separate S3 buckets (ECM, DCM, OPUS).
Once a day (or more often) we copy what the agent needs from those buckets into
**one clean set of tables that we own**, and the agent reads only those tables.

## Why bother

- **Speed.** Today every banker question re-does the heavy work: removing old
  versions, joining a dozen tables, turning codes into names. We'll do that work
  once, ahead of time, so each question only reads a small finished table.
- **Cost and load.** No more heavy queries against the shared Oracle database.
- **Simpler security.** The agent can see the finished tables and nothing else.

## The picture

```
   THE SOURCE BUCKETS  (each owned by its team; we only read them)

   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │  ECM bucket  │     │  DCM bucket  │     │ OPUS bucket  │
   │ ECM orders,  │     │ DCM deals,   │     │ deal and     │
   │ Ipreo history│     │ orders,      │     │ tranche      │
   │              │     │ hedges,trades│     │ masters      │
   └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
          │                    │                    │
          └──────────┬─────────┴──────────┬─────────┘
                     ▼                    ▼
            ┌──────────────────────────────────────┐
            │  THE LOAD JOB (scheduled)            │
            │  reads all three, cleans, joins      │
            └──────────────────┬───────────────────┘
                               ▼
   OUR AREA  (our bucket, we own it)
   ┌──────────────────────────────────────────────┐
   │ clean  : one current row per deal / tranche /│
   │          order (old versions dropped)        │
   │ serve  : the 9 finished tables the agent uses│
   └──────────────────┬───────────────────────────┘
                      ▼
          Agent (MCP server)  →  banker gets the answer
```

## Starburst words, explained

| Word | Plain meaning | In our setup |
|---|---|---|
| Bucket | A storage area in S3 where the files live | ECM, DCM, OPUS, plus one of our own |
| Catalog | Starburst's connection to one bucket | One per bucket: `ecm`, `dcm`, `opus`, `cm` (names to be confirmed) |
| Schema | A folder inside a catalog | Ours has two: `clean` and `serve` |
| Table | The data itself | The 9 finished tables in `serve` |
| Data product | A labelled, documented set of tables people can find and request access to | See below |

## Who can open what

Think of it as keys to rooms.

| Who | Has keys to | Why |
|---|---|---|
| Each source team | Their own bucket | Nothing changes for them |
| **Our load job** (one service account) | Read: ECM, DCM, OPUS. Write: our area | The only place the three buckets meet |
| **The agent** | Read: `serve` only | It can't reach raw data, even by mistake |
| Bankers | No direct access | They ask the agent; the agent's entitlement check still decides who sees ECM and who sees DCM, exactly as today |

## The data products we publish

1. **ECM Deals & Orderbook**: ECM deals, tranches, orders, allocations,
   designations, including the Ipreo history.
2. **DCM Deals & Orderbook**: DCM deals, tranches, orders, allocations, hedges,
   trades.
3. **Capital Markets (combined)**: both of the above. This is what the agent uses.

They're views over the same `serve` tables, so no data is stored twice.

## What happens when a banker asks a question

1. Banker: *"Top 10 investors on the XYZ IPO."*
2. The agent checks the banker's entitlement (ECM? DCM? both?), the same as today.
3. The agent's server builds a query against `serve`.
4. Starburst reads one small, already-clean table and answers in about a second.
   No joins across buckets happen at question time.

## What does NOT change

- The questions bankers can ask, and the answers they get.
- The agent's instructions, the catalog of fields, and the entitlement check.
- The column names: the 9 `serve` tables have exactly the columns of today's
  9 Oracle views. That is what lets us switch with a one-line change per object.

## The steps

| # | Step | Done when |
|---|---|---|
| 1 | **Port** today's 9 Oracle views to Starburst SQL, unchanged in meaning | They run against the three bucket catalogs |
| 2 | **Compare** old and new side by side, view by view | Zero differences in rows and figures |
| 3 | **Switch** the agent to the new tables | One line per object in our config, then QA |
| 4 | **Speed up**: turn the heavy views into pre-built tables in `serve`, refreshed by the load job | Same answers, faster |

## Plan B (if one account can't be given all three buckets)

Split it in two:
- An **ECM load** reads ECM + OPUS (ECM needs the OPUS deal details) and writes the ECM tables.
- A **DCM load** reads DCM only and writes the DCM tables.

The agent reads both and combines them. That works because ECM and DCM are
already kept separate inside today's views.

## What we need from the platform team

1. The catalog names for the ECM, DCM and OPUS buckets, per environment (UAT, QA, PROD).
2. Can one service account read all three? (Decides plan A or plan B.)
3. Can we have our own catalog or schema, with write access for the load job?
4. Which access-control tool is used (built-in Starburst, Ranger, Privacera)?
5. How fresh are the bucket tables compared to Oracle today, and do they keep every
   version of a row or only the latest?
6. Who signs off as owner of the data products?

## Risks, in one line each

- **Data a bit older:** the agent answers from the last load, not live data.
  That's fine because bankers ask about settled history.
- **Mismatch after the port:** caught by step 2; we don't switch until the
  comparison shows zero differences.
- **Access delays:** the questions above go out first, and plan B covers a "no".
