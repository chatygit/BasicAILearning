# 2026 Year-End Review — answers to paste

Tone: confident and results-first. State what was delivered, do not justify.
Every number comes from the Capital Markets Agent repo, its test gate or the
deploy checks; drop any you would not defend in conversation.

Suggested self-ratings: 2 on Client & Franchise and Financial Performance, where
the evidence is strongest; your call on the rest.

---

## 1. Goal descriptions (Goals tabs — replace the mid-year text)

### Risk and Control

Built risk and control into the Capital Markets Agent from day one:
entitlement-gated, read-only, fail-closed access to ECM and DCM data; no
model-written SQL; an automated control gate of 1,981 checks and 128 tests on
every change; post-deploy verification on every release. First half: delivered
my Consent Order and audit responsibilities before moving role, alongside eight
weeks of planned leave.

### Finance and Control

All training completed on time. Moved from Java to Python, Google ADK, Gemini and
MCP, and went from first commit to a Production AI agent in three months. Cut the
model's per-turn instruction cost by about a third and took core banker queries
from tens of seconds to under a second. Authored the Iceberg migration plan for
faster, cheaper data access.

### Client Franchise Outcomes

Designed, built and released to Production (25 September) the Capital Markets
Agent for Ask Banking: bankers ask in plain English and get governed answers on
deals, order books, investors, allocations, fees and Citi's role. Delivered the
Consent Order work and a full knowledge transfer, and handed over the tradebook
application, before the move.

---

## 2. WHAT Rating & Commentary

### Risk & Control

I build control in, not on. The Capital Markets Agent is entitlement-gated,
read-only and fails closed: users see only the products they are entitled to,
and the model never writes SQL. Every request is validated against a governed
catalogue before it runs. Every change passes an automated gate of 1,981 checks
and 128 tests before handover, and every database release is verified
afterwards.

I protected data accuracy for bankers. I found and fixed duplicated orders,
allocations read from the wrong source, values mixed across record versions,
missing allocations shown as zero, and convertibles labelled as shares. Each fix
was proven against the data before release. I agreed the DCM deal-status rules
with the data owner, which removed about three quarters of the rows from the DCM
order book.

I raised risks before they reached users, with evidence: database capacity (an
incident was raised), indexing, data rules and agent routing, each with the
owning team. All training was completed on time, and my Consent Order
responsibilities were delivered in the first half.

### Financial Performance

I moved from Java and Consent Order work to AI engineering and delivered a
Production agent in three months: 265 commits from 16 July to 8 October. Python,
Google ADK, Gemini, MCP and Starburst were all adopted along the way.

I made the agent cheaper and faster. The instructions the model re-reads on
every turn are about a third smaller. The most common banker queries run in under
a second instead of tens of seconds. I fixed the database memory failure that was
blocking QA.

I built it to scale without rework. Nine governed business objects mean a new
field is a catalogue entry, not new code. That is how I added a second ECM
history source (about 19,600 deals and 659,000 orders) and 24 banker filters
without a rewrite. I also wrote and presented the plan to move this data to
Iceberg on Starburst for faster, cheaper reads.

### Client & Franchise Outcomes

I designed, built and released to Production the Capital Markets Agent (25
September). Bankers ask in plain English and get governed answers from Citi's own
ECM and DCM data: deal details, order books, top investors, allocations, fees,
syndicate and Citi's role. It is held to the model-risk accuracy bar.

I turned product-owner feedback into shipped fixes in days, not sprints. That
covered convertible units, allocation accuracy, deal-type labelling, Citi-solo
deals, limit prices on scaled and convertible orders, "equity deals" excluding
convertibles, and questions routed to the wrong agent.

I widened what bankers can ask. I added the Ipreo deal history (older deals such
as the 2008 Visa IPO now answer correctly), and 24 filters: SPACs, block trades,
PIPEs, rights issues, IPO price ranges, discount to last close, upsizing, callable
and perpetual bonds, governing law, and issuer country. I recovered DCM
allocations held in a separate source, so top-investor and fill-rate answers use
the full book.

---

## 3. HOW Rating & Commentary

We Take Ownership: I owned the Capital Markets Agent end to end — architecture,
query engine, Oracle views, tests, verification and the Production release — and
fixed problems at their root, across OPUS, Orderbook, Ipreo and DataGlobe data.

We Succeed Together: I worked directly with the product owner, the ECM and DCM
data owners, DataGlobe, the DBA team and the platform team, and presented the
Iceberg migration plan to the wider team.

We Deliver with Pride: everything I ship passes an automated quality gate and
post-deploy verification, and it is documented for the next engineer.

My in-office days have been fewer than the standard because of personal
commitments. The results above are what I deliver regardless of where I sit.

Compensation: I joined three years ago at $150,000 and now earn $153,500 — about
2.3% in total over three years, below inflation, so my pay has fallen in real
terms while my scope has grown from application developer to building and
shipping a Production AI agent. I expect my compensation to
reflect the value I deliver, and I would like to discuss it this cycle.

---

## 4. Not for the form — the same point for a 1:1 or email

Send to your manager, copying his manager if you choose, before calibration
closes:

> Ahead of year-end, I want to raise compensation directly. I joined at $150,000
> three years ago and I am at $153,500 today — about 2.3% in total, below
> inflation. This year I moved into AI engineering and delivered the Capital
> Markets Agent to Production in three months. I would like my pay to reflect
> that, and I would like to agree what that looks like this cycle.

Keep it to that. Do not mention leaving unless you are ready to act on it; the
numbers make the point.
