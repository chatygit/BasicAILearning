# AskBanking AI Testing — ECM/DCM — Observations (Mike, August 18, 2026)

Transcribed from Mike's document (shared via email to Baba Chaitanya
Kothapalli + Halyna Formus for review/discussion). Faithful transcription
first; our draft answers for the discussion follow at the end.

---

## 1) What are the unwritten assumptions a tester must be aware of?

a. I know the deal must be in priced status
b. Are there some verbs or commands which are better suited than others?
   E.g. Give me, show me, what are)
c. Anything else?

## 2) Scope of Data

a. I understand AskBanking has access to "most" of OneBook data. Testers
   need to know with more detail what is in/out of scope, otherwise we
   will be failing test cases
   i. Within Deal Launcher — of the fields shown in the UI, are they all
      consumed? E.g. IssuerName, ProjectName (we discussed IssuerName is
      not, that really needs to be in DG)
      1. A field like IPO Range has different stages, are we capturing
         all stages?:
         - IPO Range Initial $10–$12
         - IPO Range Revised $11–$13

b. Within orderbook; are all the fields consumed?
   i. What about events? Orders can be modified; Do you only show the
      last version of indication and last version of allocation?

## 3) Data Dictionary

a. Can you provide some background what is stored in the data dictionary?
   In banking there are several reasons why information can be confusing
   to an LLM. Does the LLM know how to navigate equivalent names? Is
   there opportunity for PO's to enrich this or answer questions?
   - Offering = Deal
   - Symbol = Ticker
   - Priced Date = Pricing Date

b. Handling abbreviations; Technology is a value in {Sector}. If the user
   enters "tech" how will the system respond? How about "North America"
   vs. NAM. CVT = Convertible

## 4) Dealing with sub-types

There are some fields which go hand-in-hand. If the user prompts "Give me
a list of the 3 most recent convertible deals." That query is best
performed on the {Deal Type} field since it is a generic type. However,
it's probably not the best prompt.

**Acceptable Response**

| Date (Des) | Issuer Name | Deal Type |
|---|---|---|
| 8/1/26 | ABC | Convertible |
| 8/1/26 | BBB | Convertible |
| 6/1/26 | CCC | Convertible |

**Better response** — Since the prompt was so general, showing the related
sub-type field gives the user context. Is there a way for product owners
to shed light on fields which might need to be presented together, to
provide enough context?

| Date (Des) | Issuer Name | Deal Type | Sub-Type |
|---|---|---|---|
| 8/1/26 | BBB | Convertible | Convertible Bond |
| 8/1/26 | ABC | Convertible | Convertible Pfd |
| 6/1/26 | CCC | Convertible | Convertible Bond |

## 5) Sorting

While the primary sort may be related to the prompt (e.g. give me the most
recent, largest, etc.). Bankers often add a second sort, to make the data
easier to read. With two results on 8/1/26; it's best to have issuername
in alphabetical order. Is there any way to enhance?

| Date **(Des)** | Issuer Name **(Asc)** | Deal Type | Sub-Type |
|---|---|---|---|
| 8/1/26 | ABC | Convertible | Convertible Bond |
| 8/1/26 | BBB | Convertible | Convertible Pfd |
| 6/1/26 | CCC | Convertible | Convertible Bond |

## 6) How does AskBanking respond to mis-spellings?

E.g. Give me a list of rcent convrtible deals?
a. I tested this and it seemed to understand mis-spelling convertible,
   which is good.

## 7) Earlier today we demo'd AskBanking to the Banking Chief Admin officer. She had some feedback:

a. CAO — I like the summary, insight, and trends which AskBanking
   delivers after some queries
   i. I tested this and it worked. [Ask Banking link]

b. CAO — An important use case is to take a given investor and examine
   how they were allocated over various deals over a period-of-time
   i. I executed this prompt: "Look across all deals and give me
      Fidelity's indications and allocations; include the deal name and
      pricing date." It took a while and the response was "Sorry, I'm
      currently unable to provide a response. Please try again later or
      reach out to our support team @ *IBCB GLOBAL Opus AI Support for
      assistance"

c. CAO — bankers often prefer weighted averages to simple averages. Her
   opinion is that AI tends to always to go simple averages. Her ask is;
   can we set weighted averages as a preference.
   i. Mike A. — I tested this and it seems to respond correctly

   Prompt: *What is the average of 10,000 shares at $11 and 20,000
   shares at $12*

   AskBanking returned $11.67, which is correct, and not simply $11.50

   Result: [Ask Banking link]

   It also provides a comment it is outside the approved scope
   AskBanking is approved for

---
---

# DRAFT ANSWERS (ours, for the review discussion — not Mike's text)

**Standing caveat for the whole discussion: Mike is testing against the OLD
deploy.** Issuer names, billed-by, offering/equity type, regions and
settlement dates all changed in the view batches deploying this week —
observations in those areas should be re-run post-deploy, not logged as
bugs.

**1a — "deal must be priced": NOT an assumption.** There is no priced
requirement. The real rules: ECM excludes Confidential/Withdrawn/
Terminated deals at the view layer; everything else (announced, live,
draft pipeline…) is queryable via deal status. The genuine nuance is
DATES: unpriced deals have no pricing date, so any date-bounded ask
silently excludes them — the agent is trained to disclose that and offer
the status-based pipeline view instead.

**1b — verbs don't matter.** Plain questions are fine. What actually
helps: name the product when you know it (ECM vs DCM — otherwise both are
queried and results are entitlement-scoped), one ask at a time (compound
asks get split), and use ids from a previous answer for drill-downs.

**1c — the other unwritten assumptions worth telling testers:**
- QA data ≠ PROD: sparse fields (regions ~5–18%, settlement dates
  ~26–66%, some issuer masters unloaded in QA) look worse in QA than
  they will in PROD.
- Results are entitlement-scoped per user — two testers can legitimately
  get different rows.
- "This year"/"recent" resolve against the real current date (server-
  guarded).
- Long id lists cap at 40 per query; the agent batches beyond that.
- Listings are paged; "more exist" captions are honest, "N of M" totals
  only appear when a count was actually run.

**2a — scope.** In scope: deals, tranches, orders/allocations, investors
and syndicate/billing attribution from the OPUS (ECM) + OB (DCM) sources
in DataGlobe. Out of scope (other agents' domains): market prices/
valuation, institutional ownership, fees/wallet, news, documents.
- IssuerName: exactly the gap we closed this week — the fix is in the
  deploying batch (ECM names were 100% absent at source; now three-layer
  resolved). Mike's "that really needs to be in DG" is right and done.
- ProjectName: the source column EXISTS
  (OPUS_BASE_TRANSACTION.PROJECT_NAME, ECM side; no DCM equivalent).
  Not in our views yet — two measurement queries are ready
  (views/_checks/_project-name-check.sql); if population is real it joins the
  next view batch as an ECM deal field.
- IPO Range stages: NOT captured. Our views carry no price-range fields
  at all yet (base/reoffer price columns exist at source, unmeasured —
  queued as a future batch), and there is no stage history (Initial vs
  Revised) in the source tables we read. Honest answer: single current
  values only, no ranges, no stages — needs a data-team/PO conversation
  if range history matters.

**2b — orderbook events: last version only, by design.** Our views are
latest-state snapshots (versioned sources are deduped to the newest row).
No modification/event history is exposed — "how did this order change
over time" is unanswerable today and the agent says so rather than
guessing.

**3a — the data dictionary is exactly where PO enrichment goes.** Every
field carries a business description the LLM reads at query time —
synonyms, stored vocabularies, traps ("Oil & Gas" ≠ "Energy"). Mike's
three examples already work: Offering=Deal, Symbol=Ticker (a `ticker`
field exists), Priced Date=Pricing Date (the default deal date). PO
answers to open questions can be folded into these descriptions within a
day — this document's Q&A is precisely the enrichment channel.

**3b — abbreviations.**
- "tech" → Sector is a closed list of 28 stored labels; the agent
  matches case-insensitively, knows 'Technology' and 'Information
  Technology' are SEPARATE stored values, and when a guess returns 0
  rows it is told the real nearby values and discloses what it matched.
- "North America" → stored regions are NAM/EMEA/APAC (+ rare
  JAPAN/LATAM); the agent maps the phrasing. The bigger caveat is
  COVERAGE: only a minority of deals carry a region at all (QA: ~5% ECM
  / ~18% DCM), so region-filtered answers disclose that they read a
  slice.
- CVT=Convertible → understood; see 4.

**4 — sub-types: the "better response" is already the implemented rule.**
Our 2026-08-18 ruling: a "convertible deals" ask runs on the generic
class field (equity type — Convertible Preferred / Convertible Bonds…)
and the response LISTS the sub-type values alongside, exactly Mike's
second table. Product-type (sub-type) is only used as the filter when the
user names one of its exact stored values. And yes — "fields that must be
presented together" is a thing POs can specify: it goes into the field
descriptions the LLM reads (same enrichment channel as 3a).

**5 — secondary sort: DONE (applied 2026-08-18).** The query layer takes
multi-key ordering, and doctrine already required every ranked list to
end with a unique id so ties never reshuffle between pages. The skill now
also mandates the readable middle key Mike asked for: primary sort desc,
name A→Z (issuer/investor/deal), id last. Gate-pinned; no server or view
work needed.

**6 — misspellings: two layers, both safe.** Typos in the QUESTION are
absorbed by the language model ("rcent convrtible" → recent convertible).
Typos that would reach a FILTER VALUE are caught differently: values are
matched case-insensitively against stored vocabulary, and a guess that
returns 0 rows comes back with the real nearby values, so the agent
corrects and says what it matched instead of silently returning nothing.

**7a — noted; insights doctrine also forbids invented causality** (the
agent states patterns in the data, never guesses WHY).

**7b — the Fidelity failure — RESOLVED: re-ran the same prompt on the
current build (2026-08-18) and it WORKS.** Mike's failure came from an
older version — ask him to re-test and mark the case passed. The trace
analysis below stands as the record of what the old build did wrong (and
one of its flaws — misreporting an empty result as a timeout — is now
doctrine-fixed so it can't return):
The query strategy was RIGHT: the agent went directly to the order data
with an investor filter (no deal-id ferry), asked for indications and
allocations in ONE query with deal name + pricing date projected, paged
at 50 rows with a deterministic sort, and scoped to the user's entitled
products. Three real findings instead:
1. **Latency is the root cause.** The broad queries timed out at the
   database, and the turn burned ~4 sequential queries. This is the known
   V2 latency workstream (per-query credential fetch + warehouse scan
   cost on investor-name matching) — the CAO's headline use case is now
   the concrete evidence for prioritizing it.
2. **The agent's reply misreported the last query.** The date-narrowed
   retry actually RAN and returned 0 rows — an answer, not a timeout
   (likely cause: the added 5-year pricing-date window excluded the QA
   rows; date bounds also silently drop ECM orders that carry no pricing
   date). Doctrine fixed today: a timeout degrades to the cheap AGGREGATE
   (run it, don't offer it as a question), narrowing by date must be
   disclosed as a meaning change, and 0 rows is never reported as a
   timeout. Gate-pinned.
3. The offered fallback ("aggregated summary by product?") was the right
   instinct — it should simply have been executed in the same turn.

**The passing re-run (trace reviewed) shows the doctrines working
together:** the ambiguous "Fidelity" was resolved by COMBINING all four
matched entities while offering numbered narrowing ("reply with a number
from the list"); indications and allocations came back in one table per
product with unit-labelled headers ("Indication (Shares)"); and the
caption was the honest form — "Showing 1-50 of the most recent orders.
More exist." — not an invented total. One nit fed back into doctrine:
the list led with a pricing date two days in the FUTURE (a scheduled QA
test deal) without a flag; the skill now says future-dated rows in a
recency-sorted listing get a one-line "upcoming/scheduled" note.

**7c — weighted averages: the demo proves the reasoning, the data-side
gap is real and addressable.** Pure-arithmetic asks are answered
correctly (and the scope note is the guardrail working as designed). But
for DATA asks, today's server-side averages are simple AVGs — there is no
weighted-average metric exposed yet. "Weighted average as a preference"
is implementable: the POs name which weighted averages matter (e.g.
price weighted by allocated shares) and we add them as first-class
computed metrics, with doctrine to prefer them and LABEL which average
was used. Good candidate for the next enhancement round — needs the PO
definition first.
