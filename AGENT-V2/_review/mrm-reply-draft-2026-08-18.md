# Draft reply to Mike — AskBanking observations (2026-08-18)

Hi Mike,

Thanks for putting this together — very useful. Went through everything
with the engineering side; answers below, plus a few questions where we
need your/PO input.

**1) Unwritten assumptions**
- Deals do **not** need to be priced — everything except
  confidential/withdrawn/terminated ECM deals is queryable (announced,
  live, pipeline included). One nuance: deals that haven't priced have no
  pricing date, so date-bounded questions ("in 2025") won't include them;
  the agent should disclose that when relevant.
- Verbs don't matter — "give me / show me / what are" all work. What
  actually helps: mention ECM or DCM when you know it, and ask one thing
  at a time.
- Two testing tips: results are entitlement-scoped (two testers can
  legitimately see different rows), and QA data is sparse/polluted with
  test deals in places — some "missing data" is the QA copy, not the
  product.

**2) Scope**
- In scope: deals, tranches, orders/allocations, investors,
  syndicate/billing. Out of scope (other agents cover these): market
  prices/valuation, institutional ownership, fees/wallet, news,
  documents. Happy to give you a one-page in/out sheet for the testers if
  useful.
- **IssuerName** — fixed; the fix is in the view batch deploying this
  week. Please re-test after it lands.
- **ProjectName** — the source column exists and we're verifying whether
  real deals carry it (in QA it's mostly perf-test junk). One question
  back: project names are confidential code names — should AskBanking
  surface them at all?
- **IPO Range stages** — not captured today; our sources hold no
  price-range or stage history (Initial vs Revised). How important is
  this to the bankers? That decides whether we raise it with the data
  owners.
- **Orderbook events** — we show latest state only (last version of
  indication and allocation), by design. Is modification history a real
  need, or is current-state sufficient?

**3) Data dictionary**
- Yes — every field carries a business description the model reads at
  query time, including synonyms. Your three examples (Offering=Deal,
  Symbol=Ticker, Priced Date=Pricing Date) already work. This is exactly
  where PO enrichment goes: send us equivalent-name lists or "these
  fields belong together" rules and we can fold them in within a day.
- Abbreviations: "tech", NAM/"North America", CVT all resolve. One caveat
  on regions: only a minority of deals carry a region value, so
  region-filtered answers cover the deals that have one — the agent
  discloses this.

**4) Sub-types** — agreed, and that's how it works now: generic class as
the filter, sub-type shown alongside for context (your "better response"
table).

**5) Sorting** — done. Lists now sort primary (date/size) then name
alphabetically, so same-day rows read cleanly.

**6) Misspellings** — handled, as you saw.

**7) CAO feedback**
- a) Glad the insights landed.
- b) The Fidelity prompt was an older build — we re-ran it today on the
  current version and it works (entity disambiguation plus the full
  table). Please re-test and mark it passed. Generally: worth re-running
  any failures after this week's deploy.
- c) The arithmetic test proves the model computes weighted averages
  correctly. For weighted averages over *deal data*, we need the POs to
  define which ones matter (e.g., price weighted by allocated shares) —
  once defined, we add them as first-class metrics and default to them
  with a label.

**What we need from you / POs:**
1. Re-test IssuerName and the Fidelity case after this week's deploy.
2. ProjectName: should confidential code names be exposed in AskBanking?
3. IPO range/stage history: how important, banker-wise?
4. Order modification history: needed, or is latest-state fine?
5. Weighted averages: which ones, with what weights?
6. Any synonym / "present together" lists the POs have — we'll wire them
   in.

Happy to walk through any of this live.

Thanks,
Baba
