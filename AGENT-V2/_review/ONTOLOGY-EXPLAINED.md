# The Capital Markets Ontology — explained simply

*For teams who want to know how the Capital Markets Agent understands ECM and
DCM data, or who want to build something similar.*

## The idea in one paragraph

A banker asks a question in plain English. The AI model **never writes SQL**.
It fills in a short form instead: *which object, which number, broken down by
what, filtered how*. Our server checks the form against a **governed catalog of
business terms**, the ontology, and only then builds the SQL itself. If the form
asks for something the catalog doesn't define, the server refuses it and says
why. So the model can be wrong about wording, but it can't invent a column, skip
a security rule or run an arbitrary query.

## What "ontology" means here

It's a dictionary of the business, written as YAML files, one per **business
object**. Each file says:
- what the object is and what **one row** represents (its *grain*);
- which **numbers** you can ask for (*metrics*);
- which **attributes** you can show or group by (*dimensions*);
- which **filters** are allowed, with which operators;
- **rules and worked examples** that teach the model how to ask correctly.

Each object sits on one database view that returns exactly the columns the file
promises. A test checks that the two always match.

## The nine objects

| Object | One row is | Answers questions like |
|---|---|---|
| **Deal** | one deal | "How many IPOs did we do in 2025?", "Biggest DCM deals last year" |
| **Tranche** | one tranche of a deal | "Coupon and tenor of the XYZ bonds", "Who was on the syndicate?", "Gross spread on recent IPOs" |
| **Order** | one investor order | "Top 10 investors on the XYZ IPO", "How much did Fidelity get allocated?" |
| **Entity** | one name (investor, issuer, deal) | Resolving "Goldman" or a misspelt name to the right id |
| **Designation** | one ECM designation card | "Designations on deal XYZ", pot splits, selling concession |
| **Trade** | one trade | Trade book: sizes, prices, counterparties, salesperson |
| **Hedge** | one DCM hedge order | "Hedges on the XYZ deal", hedge managers and amounts |
| **Hedge trade** | one hedge execution | Executed hedge trades, direction, counterparty |
| **Trade syndicate** | one dealer on one DCM trade | Dealer designations (empty at source today) |

ECM and DCM sit side by side in the same objects, told apart by a `product`
column, so one question can cover both.

Together the nine objects define about 340 attributes, 230 filters and 60
metrics.

## The four building blocks, with examples

| Block | Plain meaning | Example from the Deal object |
|---|---|---|
| **Metric** | A number the answer is built around | `deal_count`, `total_deal_size`, `largest_deal_size` |
| **Dimension** | A column to show or group by | `deal_name`, `issuer_name`, `sector`, `last_priced` |
| **Filter** | A condition, with the operators it allows | `sector in [...]`, `last_priced gte 2025-01-01`, `subscription_ratio gt 1` |
| **Rule / example** | Guidance in business language | "ECM size is shares, DCM size is money: never rank both in one list" |

## How a question becomes an answer

```
 Banker: "List energy deals priced in 2025"
    │
    ▼
 AI model ── 1. discover_business_terms ──►  server returns the catalog
    │                                         (terms, rules, worked examples)
    │
    └────── 2. run_bqs_query (the form) ─►  server:
                                               • checks every term is in the catalog
                                               • applies the user's entitlement
                                                 (ECM, DCM or both)
                                               • builds and validates the SQL
                                               • runs it, caps the rows
                                               • returns rows + notes
    ▼
 AI model writes the answer as a table
```

The form for that question looks like this:

```yaml
source: capital_markets_deal
metric: deal_count
dimensions: [deal_name, issuer_name, sector, last_priced]
filters:
  - {field: product,     op: eq,  value: ECM}
  - {field: sector,      op: in,  value: ["Energy", "Oil & Gas"]}
  - {field: last_priced, op: gte, value: "2025-01-01"}
  - {field: last_priced, op: lt,  value: "2026-01-01"}
order: [{field: last_priced, direction: desc}]
```

The model's only job is to pick the right words from the catalog. Everything
after that is ordinary, tested code.

## Built-in safety

- **No model-written SQL.** Only catalog terms are accepted; the SQL comes from
  our code.
- **Entitlements fail closed.** A user sees only the products they're entitled
  to. If the entitlement check can't answer, nothing is returned.
- **Known gaps say so.** Questions the data can't answer, such as "matched
  orders", are listed in the catalog with a polite explanation, so the agent
  never guesses.
- **Units stay honest.** ECM is shares, DCM is money. The server attaches notes
  so the two are never mixed or ranked together.
- **Row limits** on every object, and paging for large results.
- **A gate on every change:** about 2,000 automated checks and 128 tests, run
  before anything is handed over.

## Adding something new

| You want | You change | Code change? |
|---|---|---|
| A new rule or a better example | The object's YAML | No |
| A new field that's already in the view | The object's YAML | No |
| A new field from the source tables | The view, then the YAML | No server code |
| A new kind of business object | A new view and a new YAML file | Usually none |

That's why the agent could add a second ECM history source (Ipreo, about 19,600
deals) and 24 banker filters without rewriting anything.

## What other teams can reuse

- **The pattern:** a governed catalog plus a form-filling model plus server-built
  SQL. It works for any domain where answers must be exact and access is
  controlled.
- **The objects themselves:** if your agent needs Capital Markets deal, order or
  investor data, it can call the same two tools (`discover_business_terms`,
  `run_bqs_query`) and inherit the entitlement checks and the business rules for
  free.
- **The catalog as documentation:** each YAML file reads as a data dictionary of
  ECM and DCM, with what each field means, its unit, and its traps.

## Glossary

| Term | Meaning |
|---|---|
| ECM / DCM | Equity / Debt Capital Markets, stored as `product` values |
| Grain | What one row means (one deal, one order…) |
| Ontology / catalog | The YAML files that define the business terms |
| BQS | Our query service: it turns the form into SQL |
| MCP | The protocol the AI model uses to call our two tools |
| Entitlement | Which products (ECM, DCM) a user is allowed to see |
