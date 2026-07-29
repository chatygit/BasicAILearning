# VW_DEAL_ORDER_SUMMARY — OFFICIAL data dictionary (team-shared 2026-07-30)

Transcribed from the source-mapping dictionary (ECM section + DCM section).
STATUS (user ruling 2026-07-30): SECONDARY CONTEXT ONLY - NOT the truth. The deployed schema JSON is authoritative. Already proven stale in at least one place: it lists a REGION column that does not exist in our schema. Use for hints; verify before hard enforcement.

## Per-product population matrix (the load-bearing facts)

| Column | ECM | DCM | Notes |
|---|---|---|---|
| PRODUCT | 'ECM' hardcoded | 'DCM' hardcoded | |
| DEAL_ID / DEAL_NAME | ✓ | ✓ | ECM name = SYNDICATE_DEAL_NAME |
| DEAL_SIZE | ✓ | ✓ (DEAL_ISSUE_SIZE) | dict says "monetary value" both — units doctrine (ECM=shares) came from the user; dict wording loose |
| TRANCHE_NAME / TRANCHE_SIZE | ✓ (TRANCHE_OFFER_SIZE, "deal size in shares", = dealSizeInShares in UI) | ✓ ("Total Nominal or Principal amount") | CONFIRMS units doctrine: ECM shares / DCM notional |
| PRICING_TS | ✓ | ✓ | |
| PRODUCT_CLASS | NULL | ✓ — Investment Grade, Preferred, Emerging Market, Covered Bond, High Yield, CLO, Agencies, Taxable Muni, SSA, Asset Backed, LevFin Loan, ABS, RMBS, CMBS, Municipals | |
| CURRENCY | ✓ | ✓ | |
| TRANCHE_REGION / REGION | ✓ (both = TT.REGION — duplicates on ECM) | ✓ | |
| DEAL_REGION | ✓ (OBT.DEAL_REGION) | **NULL** | |
| SENIORITY | NULL | ✓ — Senior Secured, Senior Unsecured, Junior Subordinated, Preferred, 1st/2nd/3rd Lien, ESOP, Senior Bank, Sub Bank, Senior holdco, Sub Holdco, Senior Preferred, Senior Non-Preferred, Senior Sub, FRCS, Subordinated | |
| REG_CATEGORY | NULL | ✓ — "SEC Registered(Public)", "Yankee CD", "3(A)(2) (SEC Exempt)", "144A", "Reg S", "Accredited Investors", "Domestic", "Eurobond", "Private Placement" | QA "delivery type SEC Registered" → this column, exact literal 'SEC Registered(Public)' |
| ESG_BOND | NULL | ✓ — GREEN, SUSTAINABILITY, SOCIAL | |
| ROOT_ID | = DEAL_ID | O.ROOT_ID (joins orders→deals) | |
| PARENT_ID / TRANCHE_ID | ✓ | ✓ (TRANCHE_ID derived from PARENT_ID) | |
| INVESTOR_NAME / GPNUM | ✓ | ✓ (GPNUM = O.GPID) | |
| ORDER_TYPE | ✓ | **NULL** | ⚠ dict says "LIMIT, MARKET, SCALED" — STALE: predates the IOI_TYPE split; team screenshot says values = Regular, OTT. OTT asks are ECM-ONLY either way |
| ISSUER_NAME / GFCID / TICKER | ✓ | ✓ | |
| ORDER_ID | ✓ | ✓ | confirms both-products doctrine |
| AMT | ✓?? = OI.LIMIT_VALUE ("indication amount from the IOI") | ✓ = OZ.AMT | ⚠ CONFLICTS with "AMT ≈ empty on ECM" doctrine — CONFIRM before changing metric routing; ECM AMT may be a LIMIT value, not an order amount |
| DEMAND_QTY | ✓ ("indication in shares") | ✓ = **OZ.AMT** ("demand in shares" label is wrong for DCM — it's money) | ⚠ DCM: DEMAND_QTY, AMT and ALLOCATION are ALL OZ.AMT → demand = allocation = amount on DCM → coverage/fill-rate ratios on DCM are trivially ~1x — refuse/caveat those on DCM |
| SETTLEMENT_TS | ✓ | **NULL** | flips doctrine: settlement dates/windows are ECM-ONLY |
| ALLOCATION | ✓ = O.PRIVATE_ALLOC | ✓ = OZ.AMT (mapped from order amount) | confirms per-product units |
| INVESTOR_CATEGORY(_KEY) | ✓ ("Long/Hedge", "Outright/Hedge for convertible deals") | **NULL** | investor-category asks are ECM-only |
| MEETING_TYPE(_KEY) | ✓ | **NULL** | meeting asks ECM-only |
| SECTOR | ✓ (ISSUER_INDUSTRY_SECTOR) | **NULL** | ⚠ sector asks are ECM-ONLY — DCM sector filters zero-row |
| EQUITY_TYPE | ✓ — Convertible Preferred, Common Stock, Equity Units, Warrants, Convertible Bonds, Exchangeable Notes, American Depository, Global Depository | NULL | confirms 8-value superset |
| OFFERING_TYPE | ✓ (IPO, FO) | NULL | |
| PRODUCT_TYPE | ✓ (TPD.SECURITY_TYPE_NAME) | NULL | |
| EXCHANGE | ✓ (TPD.EXCHANGE) | NULL | |
| EXECUTION_STATUS | ✓ (S.STATUS_TYPE) | NULL | |
| DEAL_STATUS | ✓ (S.STATUS_VALUE — e.g. Priced, Settled, OPEN, CLOSED) | ✓ (ODT.STATUS — Mandated, Private, Open, Closed, Archived, Cancelled) | vocab differs PER PRODUCT |
| COUPON_TYPE | NULL | ✓ — Fixed, FRN, Zero Coupon, Fixed to FRN, Fixed to Fixed, Exchanged, Structured, Funged, Step Coupon | |
| COUPON_FREQ | NULL | ✓ — Annual, Semi Annual, Quarterly, Monthly, Weekly, Zero, At Maturity, Daily | |
| USE_OF_PROCEEDS | ✓ (full list) | ✓ — General Corporate Purposes, Repay Outstanding Borrowings, Other (SMALL list) | DCM UOP vocabulary is tiny |
| SYNDICATE_MEMBER_NAME | ✓ (pipe list) | ✓ = ODT.BD_BANK (SINGLE bank — the B&D bank) | confirms single-member DCM doctrine |
| SYNDICATE_ROLE / BROKER_CODE | ✓ | **NULL** | |
| BND_BROKER | ✓ (flag per member) | = CASE WHEN BD_BANK LIKE '%Citigroup Global%' | ⚠ DCM flag literally means "is Citi" — for NON-Citi B&D on DCM use the member name, never the flag |
| IDENTIFIER_TYPE / VALUE | ✓ | ✓ (OBT_IDN) | |
| DELIVERY_TYPE | NULL | ✓ | |
| ISSUER_RATINGS | NULL | ✓ (LISTAGG comma-separated) | |
| TENORS | NULL | ✓ = TENOR_VALUE + TENOR_PERIOD, e.g. "10-YEAR" | format is '10-YEAR', not '10Y' — LIKE '%10-YEAR%' |
| SECURITIES_MATURITY | NULL | ✓ (ODT.MATURITY_DATE) | maturity asks are DCM-only |
