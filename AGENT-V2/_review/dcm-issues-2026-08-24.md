# DCM issue round — intake (opened 2026-08-24)

Same protocol as prod-issues-2026-08-21.md: one entry per issue — trace,
root cause, fix, status. SKILL/agents.yaml fixes apply immediately;
ontology/server/view causes join the release train. Release-2 configs are
applied in-repo but NOT yet deployed — check whether a reported symptom is
already fixed by release 2 before logging it as new.

## Known DCM terrain (for fast triage — measured facts, not guesses)
- TEN fields are ECM-only and hard-NULL on every DCM row (investor
  region/category, meeting/order/IOI types, offering/equity type,
  order_ownership). A DCM ask touching them = knowably-empty; the agent
  must refuse-and-offer, never run it.
- DCM demand == order_amount (same stored number); fill rate is real but
  ~4M orders carry structural zero allocation ("nothing" vs "not
  recorded" are stored identically — gt 0 filter for "actually allocated").
- deal_status carries case variants ('priced'/'Priced'); tranche and deal
  status read the SAME source column and can disagree with the deal-card
  MAX.
- Two legitimate deal-id families (I-… Ipreo + numeric) — ids are TEXT.
- Regions ~18% populated; settlement_ts rich (~66% deals) but only after
  release 2 exposes the tranche grain.
- Syndicate on DCM is a SINGLE bank string (the B&D bank), not a member
  list; billed_by = BND, 74%.
- OB_ORDER.OWNER / ALL_OWNERS exist but are UNMAPPED (semantics unknown —
  needs census before anyone promises home/away on DCM).
- DCM money needs a single currency scope; no FX column.

## Issues

(awaiting first trace)

## D1 — DCM has no transaction id in the views (user, 2026-08-24)
- **Fact base:** ECM's deal id IS the transaction id. DCM's deal id is the
  OB world's own key — but OB_DEAL_TRANCHE carries
  ORIGINATION_TRANSACTION_ID (col 212), never read by any view, absent
  from V1, never measured. Memory holds nothing more.
- **Why it's bigger than a missing column:** the DCM party-master join is
  keyed TRANSACTION_ID = DEAL_ID on an unproven assumption (QA had the
  master unloaded, so it never mattered). If the true key is the
  origination id, that join never matches in PROD — re-keying could
  unlock the DCM issuer master AND possibly DCM deal regions via
  OPUS_BASE_TRANSACTION.
- **Next:** run _checks/_dcm-transaction-id-check.sql in PROD (T1
  population/consistency, T2 format, T3 join existence, T4 payoff:
  Primary Client + region coverage). Winners = release-train: roll the id
  up to deal grain, expose it as the DCM transaction id, re-key the DCM
  PCM joins in all three views.
- **Status:** measurement queries ready; awaiting T1-T4.
