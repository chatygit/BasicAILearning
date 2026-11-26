# Column descriptions — Deal Execution data products

Paste each description into the "Column description" box, in the same order as
the screen. Tables follow the column order Starburst shows.

Descriptions marked **(confirm)** are inferred from the field name. Check them
with the ECMO team before publishing, or leave that box empty.

## Shared columns (same meaning in every dataset that has them)

| Column | Description |
|---|---|
| `_id` | Unique id of the MongoDB document (one record). |
| `rootid` | Id of the deal this record belongs to (top of the OneBook record tree). |
| `parentid` | Id of the tranche this record belongs to (the record's parent in the OneBook tree). |
| `siblingid` | Id of the related record at the same level (for trade_book: the order the trade belongs to). **(confirm)** |
| `sourcexml` | Raw XML message received from DealAxis that this record was built from. |
| `data` | The record's business fields, as one nested record. Read a field as `data.<field>`. |
| `createdtimestamp` / `createdat` | When the record was first stored in ECMO. |
| `createdby` | User or process that first stored the record. |
| `createdbyfullname` | Full name of the user who first stored the record. |
| `updatedtimestamp` / `updatedat` | When the record was last changed in ECMO. |
| `updatedby` | User or process that last changed the record. |
| `updatedbyfullname` | Full name of the user who last changed the record. |
| `version` | Record version number; higher = newer. |
| `requestversion` | Version of the request that last wrote the record. **(confirm)** |
| `source` | System the record came from. |
| `_class` | Internal application type name used by ECMO to store the record. Not business data. |

---

## dp_deal_execution_ecm_deal_tranche

### ds_onebook_orderbook_details

| Column | Description |
|---|---|
| `syndordershare` | Whether order sharing with the syndicate is enabled for this order book. |
| `autoaddpendingind` | Whether new pending indications are added to the book automatically. **(confirm)** |
| `externaldealcode` | Deal code in the external bookbuilding system; the identifier of this order book. |
| `syndordersharedetails` | Per syndicate member (by external broker code): whether it receives indications and whether indications, allocations and quality are shared with it. |
| `_class` | Internal application type name used by ECMO to store the record. Not business data. |

### ds_dealaxis_deal

| Column | Description |
|---|---|
| `_id` | Unique id of the MongoDB document (one record). |
| `data` | The DealAxis deal record (about 200 fields): book number, issuer name and symbol, offer type, deal size (initial, offered, revised, final; local and USD), filing and revised price range, offer price, bookbuild, pricing, trade and first-trade dates, fees (management, underwriting, selling concession, gross spread, praecipium, reallowance), greenshoe (granted, exercises and dates), ratings, plus nested lists of instruments, delivery identifiers (ISIN, CUSIP, SEDOL, ticker), currencies and tranches. |
| `sourcexml` | Raw XML message received from DealAxis that this record was built from. |
| `isprocessed` | Whether the ECMO DealAxis adapter has processed this record. |
| `createdtimestamp` | When the record was first stored in ECMO. |
| `createdby` | User or process that first stored the record. |
| `updatedtimestamp` | When the record was last changed in ECMO. |
| `updatedby` | User or process that last changed the record. |
| `_class` | Internal application type name used by ECMO to store the record. Not business data. |

### ds_dealaxis_syndicate

| Column | Description |
|---|---|
| `_id` | Unique id of the MongoDB document (one record). |
| `rootid` | Id of the deal this record belongs to (top of the OneBook record tree). |
| `parentid` | Id of the tranche this record belongs to (the record's parent in the OneBook tree). |
| `sourcexml` | Raw XML message received from DealAxis that this record was built from. |
| `data` | One syndicate member on a deal tranche: book number, syndicate number, member code, tranche number and member name. |
| `createdtimestamp` | When the record was first stored in ECMO. |
| `createdby` | User or process that first stored the record. |
| `updatedtimestamp` | When the record was last changed in ECMO. |
| `updatedby` | User or process that last changed the record. |
| `_class` | Internal application type name used by ECMO to store the record. Not business data. |

### ds_items_trade_refdata

Columns are not listed yet: fill them in after "Show columns" (its source is
`ecmo_items.trade_refdata`, reference data for the trade book). Use the shared
descriptions above for any shared column.

---

## dp_deal_execution_ecm_orders

### ds_ecm_orders (existing dataset, updated to the whole collection: 27 columns)

| Column | Description |
|---|---|
| `_id` | Unique id of the MongoDB document (one record). |
| `cmgindicationid` | Id of the indication in CMG (external bookbuilding feed). |
| `ipreoexternalorderid` | Id of the order in Ipreo (external bookbuilding feed). |
| `trancheid` | Tranche the order is for. |
| `version` | Record version number; higher = newer. |
| `dealid` | Deal the order is for. |
| `source` | System the order came from (for example OneBook or an external feed). |
| `orderstatus` | Current order status (for example ACTIVE, CANCELLED, PASS). |
| `ispending` | Whether the order is still pending (not yet accepted into the book). |
| `ioitype` | Indication type (for example market or limit). |
| `securitytypecode` | Type of security the order is for. |
| `ordertype` | Order type. |
| `isactive` | Whether the order is active. |
| `isdominant` | Whether this is the order that counts when the same investor's orders are matched across sources. |
| `isduplicate` | Whether the order was marked as a duplicate of another order. |
| `isowned` | Whether Citi owns (books) this order. **(confirm)** |
| `isfirmorder` | Whether the order is a firm order. |
| `ispotorder` | Whether the order is a pot (institutional pot) order. |
| `issharedorder` | Whether the order is shared with other syndicate members. |
| `ioiunit` | Unit of the indication: shares, bonds, currency amount or percent. |
| `orderioi` | The indication levels: for each level, quantity, limit value and limit type. A scaled order has several. |
| `deallinkdetails` | The deal's ids in external systems: Ipreo issue, tranche and product; CMG offering, tranche and instrument. |
| `currency` | Order currency. |
| `investordetails` | The investor: id, name, type, GP number and region. |
| `billedbybrokercode` | Code of the bank or broker billing the order. |
| `createdtimestamp` | When the record was first stored in ECMO. |
| `_class` | Internal application type name used by ECMO to store the record. Not business data. |

### ds_dealaxis_pot_order

| Column | Description |
|---|---|
| `_id` | Unique id of the MongoDB document (one record). |
| `rootid` | Id of the deal this record belongs to (top of the OneBook record tree). |
| `parentid` | Id of the tranche this record belongs to (the record's parent in the OneBook tree). |
| `sourcexml` | Raw XML message received from DealAxis that this record was built from. |
| `data` | One DealAxis pot order: book number, pot order number, investor code and name, and the order's details. |
| `createdtimestamp` | When the record was first stored in ECMO. |
| `createdby` | User or process that first stored the record. |
| `updatedtimestamp` | When the record was last changed in ECMO. |
| `updatedby` | User or process that last changed the record. |
| `_class` | Internal application type name used by ECMO to store the record. Not business data. |

### ds_dealaxis_pot_allocation

| Column | Description |
|---|---|
| `_id` | Unique id of the MongoDB document (one record). |
| `rootid` | Id of the deal this record belongs to (top of the OneBook record tree). |
| `parentid` | Id of the tranche this record belongs to (the record's parent in the OneBook tree). |
| `sourcexml` | Raw XML message received from DealAxis that this record was built from. |
| `data` | One DealAxis pot allocation: book number, pot order number, tranche number, total, pot and retention allocation, allocation price, client acknowledgement (flag, date, amount), limit type and trader. |
| `createdtimestamp` | When the record was first stored in ECMO. |
| `createdby` | User or process that first stored the record. |
| `updatedtimestamp` | When the record was last changed in ECMO. |
| `updatedby` | User or process that last changed the record. |
| `_class` | Internal application type name used by ECMO to store the record. Not business data. |

### ds_dealaxis_pot_away_order

| Column | Description |
|---|---|
| `_id` | Unique id of the MongoDB document (one record). |
| `rootid` | Id of the deal this record belongs to (top of the OneBook record tree). |
| `parentid` | Id of the tranche this record belongs to (the record's parent in the OneBook tree). |
| `sourcexml` | Raw XML message received from DealAxis that this record was built from. |
| `data` | One DealAxis "away" pot order. Same layout as pot_order. **(confirm what "away" means with the Deal Execution team)** |
| `createdtimestamp` | When the record was first stored in ECMO. |
| `createdby` | User or process that first stored the record. |
| `updatedtimestamp` | When the record was last changed in ECMO. |
| `updatedby` | User or process that last changed the record. |
| `_class` | Internal application type name used by ECMO to store the record. Not business data. |

### ds_dealaxis_pot_away_allocation

| Column | Description |
|---|---|
| `_id` | Unique id of the MongoDB document (one record). |
| `rootid` | Id of the deal this record belongs to (top of the OneBook record tree). |
| `parentid` | Id of the tranche this record belongs to (the record's parent in the OneBook tree). |
| `sourcexml` | Raw XML message received from DealAxis that this record was built from. |
| `data` | One DealAxis "away" pot allocation. Same layout as pot_allocation. **(confirm)** |
| `createdtimestamp` | When the record was first stored in ECMO. |
| `createdby` | User or process that first stored the record. |
| `updatedtimestamp` | When the record was last changed in ECMO. |
| `updatedby` | User or process that last changed the record. |
| `_class` | Internal application type name used by ECMO to store the record. Not business data. |

---

## dp_deal_execution_ecm_trades

### ds_items_trade_book

| Column | Description |
|---|---|
| `_id` | Unique id of the MongoDB document (one record). |
| `rootid` | Id of the deal this record belongs to (top of the OneBook record tree). |
| `parentid` | Id of the tranche this record belongs to (the record's parent in the OneBook tree). |
| `siblingid` | Id of the related record at the same level (for trade_book: the order the trade belongs to). **(confirm)** |
| `itemtype` | Kind of trade-book item. |
| `data` | The trade: order, tranche and deal ids, tranche and issue name, investor name and the rest of the trade's fields. |
| `ecmoupdated` | When or whether ECMO last updated the item. **(confirm)** |
| `createdtimestamp` | When the record was first stored in ECMO. |
| `createdby` | User or process that first stored the record. |
| `updatedtimestamp` | When the record was last changed in ECMO. |
| `updatedby` | User or process that last changed the record. |
| `version` | Record version number; higher = newer. |
| `source` | System the record came from. |

### ds_items_trade_designations

| Column | Description |
|---|---|
| `_id` | Unique id of the MongoDB document (one record). |
| `investorname` | Investor on the designation card. |
| `dealid` | Deal the designation is for. |
| `submissionstatus` | Submission status of the designation. |
| `cardsstatus` | Status of the designation card. |
| `tradedate` | Trade date on the card. |
| `tradeid` | Trade the designation belongs to. |
| `settlementdate` | Settlement date on the card. |
| `firmaccount` | Firm account on the card. |
| `side` | Side of the card (buy or sell). |
| `salesid` | Salesperson id. |
| `gpnumber` | Investor's GP number (Citi's client id). |
| `currency` | Card currency. |
| `quantity` | Card quantity. |
| `designableshares` | Shares available to designate. |
| `potsplit` | Pot split amount. |
| `sellingconcession` | Selling concession on the card. |
| `underwritingfees` | Underwriting fees on the card. |
| `managementfees` | Management fees on the card. |
| `ev` | EV figure on the card. **(confirm)** |
| `securityidtype` | Type of security identifier (CUSIP, ISIN…). |
| `securityid` | Security identifier. |
| `issuetypecode` | Issue type code. |
| `status` | Overall designation status. |
| `brokername` | Designated broker or syndicate member. |
| `brokercode` | Code of the designated broker. |
| `missingfields` | Fields still missing before the card can be submitted. |
| `trancheid` | Tranche the designation is for. |
| `tranchename` | Tranche name. |
| `stpupdated` | Whether the card was updated by straight-through processing. |
| `cardssendingtype` | How the card is sent. **(confirm)** |
| `designationtype` | Designation type. |
| `externaldealcode` | Deal code in the external bookbuilding system. |
| `ipreoexternaltranchecode` | Tranche code in Ipreo. |
| `potsplitpercentage` | Pot split percentage. |
| `createdat` | When the record was first stored in ECMO. |
| `createdby` | User or process that first stored the record. |
| `updatedat` | When the record was last changed in ECMO. |
| `updatedby` | User or process that last changed the record. |
| `requestversion` | Version of the request that last wrote the record. **(confirm)** |

### ds_items_underwriting_trade_book

| Column | Description |
|---|---|
| `_id` | Unique id of the MongoDB document (one record). |
| `dealid` | Deal the underwriting trade is for. |
| `citirole` | Citi's role on the trade. |
| `bookingtype` | Booking type. |
| `bookingaccountidtype` | Type of the booking account id. |
| `securityid` | Security identifier. |
| `securityidtype` | Type of security identifier (CUSIP, ISIN…). |
| `contramnemonic` | Counterparty mnemonic. |
| `firmmnemonic` | Citi firm account mnemonic. |
| `bsfirmview` | Buy or sell, from the firm's side. **(confirm)** |
| `quantity` | Trade quantity. |
| `price` | Trade price. |
| `salesid` | Salesperson id. |
| `commission` | Commission. |
| `traderid` | Trader id. |
| `counterpartyaccountidtype` | Type of the counterparty account id. |
| `blottercode` | Trading blotter code. |
| `fccode` | FC code. **(confirm)** |
| `isclosed` | Whether the trade is closed. |
| `currentstate` | Current state of the trade. |
| `action` | Last action taken on the trade. |
| `createdat` | When the record was first stored in ECMO. |
| `createdby` | User or process that first stored the record. |
| `createdbyfullname` | Full name of the user who first stored the record. |
| `updatedat` | When the record was last changed in ECMO. |
| `updatedby` | User or process that last changed the record. |
| `updatedbyfullname` | Full name of the user who last changed the record. |
| `requestversion` | Version of the request that last wrote the record. **(confirm)** |
