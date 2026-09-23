# Cross-service integration guide

Inspection date: 2026-09-23  
Repository: `https://github.com/Al1husse1n/backend-engine.git`  
Branch: `main` (matches `origin/main`)  
Commit: `d403563` — Merge pull request #2 from `Al1husse1n/brooksv1`  
Original core API: pull request #1, merge `d7c7683` (`feat: implement core business API`, 2026-09-18)

This file describes the backend integration contract. It is written so it can be copied into the Voxide repository.

Startup repair after the `d403563` assessment: `app/main.py` again loads the original router only. `app.models` is a package; `Event` lives in `app/models/event.py` and is the only model `init_db` creates. `Business`, `InventoryItem`, and `EventLog` import, sit on `RelationalBase`, and are not created or served. `python -m pytest`: 35 passed. The HTTP contract is unchanged.

Labels used below:

- **Implemented** — present in code that the application actually loads, or in the written contract that code follows.
- **Present but unwired** — files exist on `main`, but nothing that serves HTTP uses them, and several of them cannot be imported.
- **Recommendation** — not implemented. Do not treat these as an existing API.

`README.md` describes the served API. The detailed contract is `docs/API_CONTRACT.md` plus the handlers under `app/services/`. Empty route files and `app/core/` are not part of that API.

---

## Project context

STARK Hackathon 2026. The product is a voice-first business assistant for a small business. Three services share one business API:

| Service | Owns | Does not own |
| --- | --- | --- |
| Backend (`backend-engine`) | Validation, business rules, persistence, deterministic totals, stock, and debt | Speech, TTS, LLM intent parsing |
| Voxide | Speech-to-text, text-to-speech, voice turn-taking, turning speech into the JSON this API already accepts | Ledger totals, stock math, debt balances, the database |
| Frontend | Text and voice UI, language selection, showing backend `message` / clarification / errors | Business rules and stored business state |

The backend is the source of truth. LLM memory, the frontend, and Voxide state are not.

There is **no authentication**. `business_id` is a client-supplied string. The local frontend currently sends `business_123`.

---

## Current implementation status

### What is actually implemented

The core API from pull request #1 is still the only API:

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/` | Service banner. Returns `service`, `docs`, `health`. |
| `GET` | `/api/v1/health` | Liveness. Body: `{"status": "ok"}`. |
| `POST` | `/api/v1/events` | Validate and append one business event. `201` on success. |
| `POST` | `/api/v1/query` | English keyword question against stored events. `200` on success. |

Supported event types: `sale`, `expense`, `purchase`, `inventory_adjustment`, `customer_debt`.

Supported query types, chosen by an English keyword parser (not an LLM):

- `sales_total`
- `expenses_total`
- `purchases_total`
- `expenses_top`
- `inventory_quantity`
- `customer_debt`

Persistence is one append-only SQLite table, `events`. Inventory quantity and customer balances are **calculated from those rows at query time**. They are not stored as current balances.

Natural-language **questions** are interpreted inside the backend (`app/services/query.py`). Natural-language **commands** are not. `app/services/extraction.py` is only a `Protocol`. Callers must already send structured event JSON.

### What changed after the original core API

Pull request #2 (`44c39cd`, `d022406`, merged by `d403563` on 2026-09-22) did **not** replace the core API. It added a second, unfinished layout and rewrote the README. `docs/API_CONTRACT.md`, `requirements.txt`, `.env.example`, and the tests were not updated to match that README.

Concrete changes on top of `d7c7683`:

1. `app/main.py` was edited so the process could not start. That overlay has been removed. The app again includes `api_router` once. See “Startup” below.
2. Empty route files were added and are not mounted: `auth.py`, `users.py`, `business.py`, `sales.py`, `expenses.py`, `purchases.py`, `inventory.py`, `debts.py`, `analytics.py`, `payments.py`, `dependencies.py`.
3. Empty schema files: `schemas/auth.py`, `business.py`, `inventory.py`, `ledger.py`, `user.py`.
4. Empty models: `models/payment.py`, `models/user.py`.
5. Empty services: `events/debt_service.py`, `expense_service.py`, `purchase_service.py`, `payment_service.py`.
6. A duplicate router was added twice, as `app/api/v1/router.py` and `app/api/v1/endpoints/agent_gateway.py`. The live router is `app/api/v1/__init__.py`. It does not include either file. There is **no** `POST /api/v1/agent-gateway` route.
7. A second settings/database/error stack was added under `app/core/`. The running app uses `app/config.py`, `app/db.py`, and `app/errors.py`.
8. New ORM models were added under `app/models/` (`Business`, `InventoryItem`, `EventLog`). They are sketches, not the tables the live app creates. The `app/models.py` / `app/models/` clash is resolved: `Event` is `app/models/event.py`, exported from `app/models/__init__.py`.
9. `app/models/base.py` had been a copy of the JWT helper. It is now `RelationalBase` plus `AuditMixin`. The sketch models use that base. `init_db` does not import them, so their tables are not created. JWT helpers remain only in the unused `app/core/security.py`.
10. `app/services/events/sale_service.py` and `app/services/analytics_service.py` are partial async implementations aimed at the unwired models. They are not called by the live routes. Their behavior disagrees with the live handlers (see “Do not integrate against the unwired stack”).
11. `requirements.txt` still has no `passlib`, `python-jose` / `jose`, or `aiosqlite`. The new security and async database modules cannot import in this environment.
12. Tests still describe the original contract. After the startup repair they collect and pass (35 tests).

### Startup

PR #2 appended three lines that imported `sqlalchemy.engine` as if it were a connection, included the router again with `settings.API_V1_STR` (that attribute exists only on the unused `app.core.config.Settings`), and called `engine.begin()` on the SQLAlchemy engine module. Those lines are gone.

The served routes are again only:

- `GET /`
- `GET /api/v1/health`
- `POST /api/v1/events`
- `POST /api/v1/query`

`app.main` imports. `python -m pytest` passed 35 tests after the repair.

### Do not integrate against the unwired stack

If someone later mounts `app/api/v1/router.py` or `agent_gateway.py` without rewriting them, callers would see different behavior:

- Only `event_type == "sale"` is sent to `process_sale_event`. Every other type returns id `evt_generic` and **does not persist**.
- Sale quantity defaults to `1` when omitted. The live API asks for clarification instead.
- Sale `item` is optional. The live API requires it.
- Stock is decremented only when an `InventoryItem` row already exists. The live API never writes a stock table; it derives quantity from events and allows the derived quantity to go negative.
- The query helper treats any text containing `sell`, `sold`, or `sale` as all-time sales, but the message says “today” and the period is always today’s date. The live parser filters on the event’s `data.date`.
- `NeedsClarificationError` in `app/core/errors.py` is written to return HTTP 200. The live clarification handler returns HTTP 400. The core handlers are not registered on the FastAPI app.
- The old README success example (`event_id`, `data.remaining_stock`) matched neither the live response nor `sale_service.py`. The README now shows the live `event.id` envelope.

**Recommendation:** keep Voxide and the frontend on `POST /api/v1/events` and `POST /api/v1/query`. Do not call `/api/v1/agent-gateway`. Do not add JWT headers. Do not expect `remaining_stock` in the response.

---

## Current backend architecture

### Live components

```text
HTTP
  app/main.py
    CORS from CORS_ORIGINS
    exception handlers in app/errors.py
    lifespan: app.db.init_db() creates tables
    router: app/api/v1/__init__.py
      GET  /api/v1/health     app/api/v1/health.py
      POST /api/v1/events     app/api/v1/events.py
      POST /api/v1/query      app/api/v1/query.py

POST /events
  EventRequest (app/schemas.py, extra fields forbidden)
  app/services/events/registry.py process_event
    handler.validate → normalize
    insert Event
    handler.success_message

POST /query
  QueryRequest
  app/services/query.py answer_query
    load this business_id's events
    parse English text into one QueryIntent
    sum or derive from those rows
```

| Module | Role |
| --- | --- |
| `app/config.py` | Live settings. Env file `.env`. Unknown env vars ignored. |
| `app/db.py` | Sync SQLAlchemy engine, session, `create_all`. Default URL `sqlite:///./data/app.db`. |
| `app/models/event.py` | Live model, `Event`, table `events`. Exported from `app/models`. |
| `app/schemas.py` | Request and success models for events and queries. |
| `app/errors.py` | `VALIDATION_ERROR` and `NEEDS_CLARIFICATION` JSON. |
| `app/services/normalization.py` | Numbers, dates, currency, blank checks. Default currency `ETB`. |
| `app/services/events/*.py` | One handler per event type. This is the business logic. |
| `app/services/query.py` | English parser plus deterministic answers. |
| `app/services/extraction.py` | Interface only. No extractor is implemented. |

`get_db()` commits on success and rolls back on exception. A clarification or validation error does not leave a row.

### Database the live app creates

Table `events` (append-only):

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string PK | `event_` + UUID |
| `business_id` | string, indexed | Client-supplied. No `businesses` table. |
| `event_type` | string, indexed | One of the five supported types. |
| `language` | string | Stored. Not used by calculation. |
| `data` | JSON | Normalized event fields. |
| `created_at` | timezone-aware datetime | Insert time. Queries do **not** filter on this. |

There is no users table, no stock table, no debt table, and no payments table in the live schema.

Period filters use `data.date` (`YYYY-MM-DD`), not `created_at`.

### How state is calculated

All math happens in `answer_query` after rows are loaded for one `business_id`.

**Sales total.** Sum of `data.amount` on `sale` rows in the period. Optional item filter, case-insensitive, whitespace-collapsed. Result also includes `count`. If an item was detected, `quantity` is the sum of `data.quantity` on the matched sales.

**Expenses total.** Sum of `data.amount` on `expense` rows in the period. No category filter.

**Purchases total.** Same pattern for `purchase` rows. Optional item filter.

**Biggest expenses.** Up to 5 `expense` rows in the period, sorted by amount descending. Fields returned: `description`, `amount`, `currency`, `date`.

**Inventory.** For one item name:

- `purchase` adds `quantity`
- `sale` subtracts `quantity`
- `inventory_adjustment` adds the signed `quantity` (negative decreases)

No floor. A sale of more units than purchased yields a negative quantity. Name match is case-insensitive. The word `today` (and other parser keywords) is never treated as an item name.

**Customer debt.** Net per customer name (case-insensitive):

- `direction: owed_to_business` increases what the customer owes the business
- `direction: owed_by_business` decreases that balance (the business owes the customer)

A named-customer query returns the net, including zero. A “who owes me” query lists only customers whose net is **positive**, plus a `total`.

Mixed currencies in one answer collapse to `ETB` unless every matched row has the same currency.

### Validation behavior

Two different failures:

| Situation | HTTP | Body |
| --- | --- | --- |
| Required information missing | 400 | `success: false`, `status: "needs_clarification"`, `message`, `missing_fields`, and `error.code: "NEEDS_CLARIFICATION"` |
| Value present but illegal, or unsupported event type | 400 | `success: false`, `error.code: "VALIDATION_ERROR"`, `error.message`. No `missing_fields`. |
| FastAPI missing top-level JSON fields (`business_id`, `language`, `event_type`, or `query`) | 400 | Clarification shape, `missing_fields` lists those names, message `"Required information is missing."` |
| Other malformed JSON (extra fields, wrong types at the top level) | 400 | `VALIDATION_ERROR` and the first Pydantic message |

Event `data` is a free object at the schema layer (`extra` is forbidden only on the **outer** request). Handlers then require the fields for that event type.

Empty string is missing. Numbers may be numeric or numeric strings (`"900"`, `"1,200"`). Booleans are rejected as numbers. Integer-valued floats are stored as integers (`3.0` → `3`).

Dates: omitted, null, or blank becomes the server’s local calendar date (`date.today()`), ISO `YYYY-MM-DD`. Any other value must already be `YYYY-MM-DD`. Datetimes and natural-language dates are rejected.

Currency: omitted becomes `ETB`. Otherwise the string is stripped and uppercased. There is no allow-list.

`language` on an event must be a non-empty string. It is stored and does not change validation. `language` on a query must be English (`en`, `eng`, `english`, or a subtag whose primary tag is `en`, such as `en-US`). Any other language returns clarification even if the query text is English: `"Query interpretation currently supports English only. Please ask in English."`

### Query parser limits (implemented)

The parser is keyword-based and English-only. It refuses to guess when two intents match.

Clarification examples that are tested:

- Unrecognized text (`"Tell me a joke"`)
- Inventory question with no item (`"How many do I have left?"`)
- Both spend and buy (`"How much did I spend buying stock?"`)
- Sales plus “left” without a clear stock question (`"What sales are left to record?"`)
- Supplier / “who do I owe” wording (`"Who do I owe?"`, `"How much does the business owe suppliers?"`)
- Non-English `language` value

Periods:

| Phrase | Window |
| --- | --- |
| `today`, `tonight` | That calendar day |
| `this week`, `the week` | Monday through today (`date.weekday()`, Monday = 0) |
| `this month`, `the month` | First of the month through today |
| anything else | All stored dates |

“Week” is not the last 7 days. There is no custom date range in the query language.

Item detection prefers names already stored for that business, longest first, whole word, case-insensitive. A fallback grabs the noun in “how many …”. Reserved words (`today`, `left`, `cost`, `sale`, `owe`, …) are never item names.

Customer detection is the pattern `how much does <Name> owe` or `does <Name> owe`. One Latin-letter token (`A-Za-z`, apostrophe, hyphen). `"Hana"` works. Multi-word names and non-Latin names are not extracted by this regex.

### Not implemented

These were described by the pre-repair README. They are still not served, not enforced, and not in `requirements.txt`. The current README does not document them as available:

- Signup, login, JWT, password hashing, roles
- `POST /api/v1/agent-gateway`
- Per-resource routes for users, businesses, sales, expenses, purchases, inventory, debts, analytics, payments
- PostgreSQL as a configured default (the live default is SQLite; a URL can be swapped via `DATABASE_URL`)
- Async SQLAlchemy runtime
- Subscriptions
- Stock row updates and `remaining_stock`
- Multi-tenant checks beyond “filter rows by the `business_id` string you sent”
- Advice (“should I buy more stock?”)
- Scholarxiv / external research
- An LLM inside this repository

---

## Current API contract

Base path: `/api/v1`. Production host is deployment-specific. Local bind defaults to `0.0.0.0:8000`. Interactive docs are at `/docs`.

No `Authorization` header is read. CORS: `CORS_ORIGINS` comma-separated, or `*` (default) without credentials.

### `GET /api/v1/health`

No body.

`200`:

```json
{ "status": "ok" }
```

### `GET /`

`200`:

```json
{
  "service": "backend-engine",
  "docs": "/docs",
  "health": "/api/v1/health"
}
```

### `POST /api/v1/events`

Records one event after validation. Does not interpret a sentence. Does not update a second balance table.

#### Request

```json
{
  "business_id": "business_123",
  "language": "en",
  "event_type": "sale",
  "data": {
    "item": "shirts",
    "quantity": 3,
    "amount": 900,
    "currency": "ETB",
    "customer": null,
    "date": "2026-09-17"
  }
}
```

| Field | Required | Rule |
| --- | --- | --- |
| `business_id` | yes | Non-empty string. Whitespace-only is `VALIDATION_ERROR`. Not checked against a registry. |
| `language` | yes | Non-empty string. Stored. Any language code is accepted on this endpoint. |
| `event_type` | yes | `sale`, `expense`, `purchase`, `inventory_adjustment`, `customer_debt`. Anything else: `VALIDATION_ERROR` listing the supported types. |
| `data` | yes as an object | Defaults to `{}` if omitted, then the handler asks for its required fields. |

Unknown top-level fields are rejected (`extra: forbid`).

#### Success — `201`

```json
{
  "success": true,
  "event": {
    "id": "event_<uuid>",
    "event_type": "sale",
    "data": {
      "item": "shirts",
      "quantity": 3,
      "amount": 900,
      "currency": "ETB",
      "customer": null,
      "date": "2026-09-17"
    }
  },
  "message": "Sale recorded successfully: 3 shirts for 900 ETB."
}
```

`event.data` is the normalized object (trimmed strings, numbers coerced, default currency and date filled in). The message is English and safe to read aloud. It is not translated to `language`.

#### Sale `data`

| Field | Required | Rule |
| --- | --- | --- |
| `item` | yes | Non-empty string. Prompt: “Which item was sold?” |
| `quantity` | yes | Number > 0. Zero or negative: `VALIDATION_ERROR`. |
| `amount` | yes | Number > 0. This is the money total for the line, not a unit price. |
| `currency` | no | Default `ETB`. |
| `customer` | no | String or null. Blank becomes null. |
| `date` | no | `YYYY-MM-DD` or server today. |

Success message: `Sale recorded successfully: {quantity} {item} for {amount} {currency}.`

#### Expense `data`

| Field | Required | Rule |
| --- | --- | --- |
| `description` | yes | “What was the expense for?” |
| `amount` | yes | > 0 |
| `currency` | no | Default `ETB` |
| `category` | no | String or null |
| `date` | no | ISO date or today |

Success message: `Expense recorded successfully: {amount} {currency} for {description}.`

#### Purchase `data`

| Field | Required | Rule |
| --- | --- | --- |
| `item` | yes | “Which item was purchased?” |
| `quantity` | yes | > 0. This increases derived stock. |
| `amount` | yes | > 0. Money spent, not a unit cost used later. |
| `currency` | no | Default `ETB` |
| `supplier` | no | String or null |
| `date` | no | ISO date or today |

Success message: `Purchase recorded successfully: {quantity} {item} for {amount} {currency}.`

#### Inventory adjustment `data`

| Field | Required | Rule |
| --- | --- | --- |
| `item` | yes | “Which item should be adjusted?” |
| `quantity` | yes | Non-zero number. Positive adds, negative removes. Zero is `VALIDATION_ERROR`. |
| `reason` | yes | “Why is inventory being adjusted?” |
| `date` | no | ISO date or today |

No amount and no currency.

Success message: `Inventory adjustment recorded: {item} increased|decreased by {abs(quantity)}.`

#### Customer debt `data`

| Field | Required | Rule |
| --- | --- | --- |
| `customer` | yes | “Which customer is this debt for?” |
| `amount` | yes | > 0 |
| `direction` | yes | Exactly `owed_to_business` or `owed_by_business`. Other values: `VALIDATION_ERROR`. |
| `currency` | no | Default `ETB` |
| `date` | no | ISO date or today |

There is no separate “payment” event. Recording the opposite direction reduces the net the next time debt is queried. Sending the same direction again **adds** another amount; it does not replace the balance.

Success messages:

- `Customer debt recorded: {customer} owes {amount} {currency}.`
- `Customer debt recorded: business owes {customer} {amount} {currency}.`

#### Clarification example

Missing sale amount, nothing stored:

```json
{
  "success": false,
  "status": "needs_clarification",
  "message": "What amount was the sale?",
  "missing_fields": ["amount"],
  "error": {
    "code": "NEEDS_CLARIFICATION",
    "message": "What amount was the sale?"
  }
}
```

When several fields are missing, `missing_fields` lists all of them. `message` asks about the first one only.

#### Validation example

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Amount must be greater than zero."
  }
}
```

### `POST /api/v1/query`

#### Request

```json
{
  "business_id": "business_123",
  "language": "en",
  "query": "How much did I sell today?"
}
```

| Field | Required | Rule |
| --- | --- | --- |
| `business_id` | yes | Non-empty. Scopes every read. |
| `language` | yes | Must be English for parsing to run. |
| `query` | yes | Non-empty English question. |

#### Success — `200`

```json
{
  "success": true,
  "query_type": "sales_total",
  "result": {
    "amount": 4500,
    "currency": "ETB",
    "count": 2,
    "period": { "start": "2026-09-23", "end": "2026-09-23" }
  },
  "message": "You sold 4,500 ETB today."
}
```

`period` is omitted when the question has no today/week/month phrase (all-time). Whole numbers are JSON integers. `message` is English.

#### Result shapes

**`sales_total`**

- Always: `amount`, `currency`, `count`
- If a period was detected: `period.start`, `period.end`
- If an item was detected: `item`, `quantity`
- Message: `You sold {amount} {currency}[ of {item}][ today| this week| this month].`

**`expenses_total`**

- `amount`, `currency`, `count`, optional `period`
- Message: `You spent {amount} {currency}...`

**`purchases_total`**

- `amount`, `currency`, `count`, optional `period`, optional `item`
- Message: `You spent {amount} {currency} on purchases[ of {item}]...`
- “What's the cost of my purchases?” is a purchase total, not an expense total.

**`expenses_top`**

```json
{
  "expenses": [
    {
      "description": "rent",
      "amount": 5000,
      "currency": "ETB",
      "date": "2026-09-23"
    }
  ],
  "period": { "start": "2026-09-01", "end": "2026-09-23" }
}
```

Message names the largest row, or `No expenses were recorded...` when the list is empty.

**`inventory_quantity`**

```json
{ "item": "shirts", "quantity": 17 }
```

Message: `You have 17 shirts left.` The `item` string is the name as previously stored when it matched a known item, otherwise the phrase extracted from the question.

**`customer_debt` named customer**

```json
{
  "customer": "Hana",
  "amount": 600,
  "currency": "ETB",
  "direction": "owed_to_business"
}
```

`direction` is `owed_by_business` when the net is negative. Amount is the absolute net in the stored currency field (the sign is carried by `direction` and by the message). Zero net: “{customer} does not currently owe you money.” Unknown customer: amount `0`, currency `ETB`, same zero message.

**`customer_debt` list** (`Who owes me money?`)

```json
{
  "customers": [
    { "customer": "Hana", "amount": 600, "currency": "ETB" }
  ],
  "total": 600,
  "currency": "ETB"
}
```

Only positive nets. Message lists `Name (amount currency)`, or `Nobody currently owes you money.`

#### Clarification — `400`

Same envelope as events. `missing_fields` is often `["query"]` or `["item"]`.

```json
{
  "success": false,
  "status": "needs_clarification",
  "message": "I could not tell what you want to know. Try asking about sales, expenses, inventory, or money a customer owes you.",
  "missing_fields": ["query"],
  "error": {
    "code": "NEEDS_CLARIFICATION",
    "message": "I could not tell what you want to know. Try asking about sales, expenses, inventory, or money a customer owes you."
  }
}
```

An empty result is still success. “How much did I sell today?” with no sales returns `amount: 0` and a normal message. It does not 404.

### Contract changes since the original implementation

**The HTTP contract in `docs/API_CONTRACT.md` was not changed.** Request fields, the five event types, success envelopes, and the clarification envelope are the same ones the frontend already calls.

The pre-repair README described an agent gateway and per-resource routes. Those routes were never registered. The README again documents only `/health`, `/events`, and `/query`.

Small behaviors that are easy to miss, all from the original implementation (not from PR #2):

- Success responses do not include `language`, `business_id`, or `created_at`.
- Query `result` always includes `count` for the three money totals. The contract’s short example omitted `count`.
- Inventory and debt responses do not use the sales-style `amount`/`period` example.
- There is no list-history endpoint (no “show my last 10 sales”).
- Expenses cannot be queried by category, even though category can be stored.
- Advice and Scholarxiv are documented as non-goals or future work and have no route.

---

## Business operations

Each write is one row in `events`. Nothing here is idempotent. A retried voice turn creates a second row.

| Operation | Required data | Optional | Persistence | Derived state | Safe for voice without confirmation? |
| --- | --- | --- | --- | --- | --- |
| Record sale | `item`, `quantity` > 0, `amount` > 0 | `currency`, `customer`, `date` | Append `sale` | Lowers derived stock by `quantity`. Adds to sales totals. Does not create a debt. | **No.** Confirm, then `POST /events`. |
| Record expense | `description`, `amount` > 0 | `currency`, `category`, `date` | Append `expense` | Adds to expense totals. Does not change stock. | **No.** |
| Record purchase | `item`, `quantity` > 0, `amount` > 0 | `currency`, `supplier`, `date` | Append `purchase` | Raises derived stock. Adds to purchase totals. Distinct from expenses. | **No.** |
| Adjust inventory | `item`, non-zero `quantity`, `reason` | `date` | Append `inventory_adjustment` | Adds signed quantity to stock. | **No.** |
| Record customer debt | `customer`, `amount` > 0, `direction` | `currency`, `date` | Append `customer_debt` | Recomputes that customer’s net. Does not change stock or sales. | **No.** |
| Ask a question | English `query`, `business_id`, `language: "en"` | — | Nothing | Reads and sums events | **Yes.** Call `POST /query` directly. |
| Health | — | — | Nothing | — | **Yes.** |

**Recommendation:** confirmation applies to every `POST /events` call. Read-only calls do not need confirmation. The backend itself will persist as soon as validation passes; it has no confirm/cancel step.

A sale on credit is two operations if both stock and debt should change: a `sale` and a `customer_debt`. The backend does not infer debt from a customer name on a sale.

A repayment is another `customer_debt` with `direction: "owed_by_business"` (customer paid, so the business’s receivable falls) only if that matches the product meaning the team wants. The handler does not have a `repayment` type. Say the direction explicitly in the payload. Do not invent a sixth event type.

Operations the backend will reject or cannot do:

- Payroll or any other `event_type`
- Editing or deleting an event
- Setting stock to an absolute count (only deltas)
- Querying “who do I owe?” or supplier payables as a first-class answer (the parser asks for clarification; `owed_by_business` is stored but “who do I owe” is not implemented)
- Expenses by category
- Date-range questions other than today / this week / this month / all time
- Advice, forecasts, unit-cost margins
- Any request whose `language` is not English on `/query`

---

## Data and state ownership

| Concern | Source of truth | Who may interpret | Who must validate, calculate, and persist |
| --- | --- | --- | --- |
| Sales | `events` where `event_type = sale` | Voxide may extract item, quantity, amount, customer, date from speech | Backend validates and inserts. Totals come only from `POST /query`. |
| Expenses | `events` where `event_type = expense` | Voxide may extract description, amount, category, date | Backend |
| Purchases | `events` where `event_type = purchase` | Voxide may extract item, quantity, amount, supplier, date | Backend. Purchase money is not an expense. |
| Inventory | Derived from purchase, sale, and adjustment quantities | Voxide may extract the adjustment the user asked for | Backend. Voxide must not keep a stock cache as truth. |
| Customer debts | Derived net of `customer_debt` rows | Voxide may extract customer, amount, and direction | Backend. Voxide must not keep a balance cache as truth. |
| Query answers | Computed on read from the rows above | Voxide may turn speech into an English question string | Backend parser + SQL/Python sums. The `message` is the verified sentence. |
| Business identity | The `business_id` string the client sends | Frontend/Voxide must send the same id the user is operating as | Backend does not authenticate it. |
| Language of the conversation | Not business state | Voxide and frontend | Stored on events only. Query parsing requires English text and `language: "en"`. |

Voxide should interpret **intent and slots**. It should not decide that a number is “valid enough” to skip the backend, and it should not compute “you have 17 left” itself.

If the backend returns clarification, the missing slots are still unknown. Do not fill them with a model guess and retry silently.

---

## Voxide integration boundary

### Recommended boundary

```text
User speaks
    → Voxide: STT in the user’s language
    → Voxide: classify intent
         question → translate the question to English if needed
                  → POST /api/v1/query
                  → speak backend message (or speak clarification question)
         write    → extract structured slots
                  → if slots missing, ask in the user’s language (do not POST yet)
                  → read the structured action back and wait for confirmation
                  → POST /api/v1/events
                  → speak backend message, or speak clarification / error
    → Voxide: TTS
```

The frontend may own the HTTP calls (Voxide produces text/slots, frontend posts). That matches the current frontend, which already posts to these two routes and has no voice stack. Either of these is compatible with the backend:

1. **Voxide → frontend → backend.** Voxide returns transcript, intent, and slots to the UI. The UI posts JSON. Use this if the browser is already the only HTTP client.
2. **Voxide → backend, frontend observes.** Voxide posts the same JSON itself. The UI still needs the response if it displays history.

**Recommendation:** prefer (1) for the hackathon if the frontend session already holds `business_id` and the API base URL. The backend does not care which process is the HTTP client. It does care that the body is the contract above, not audio and not a Voxide-specific envelope.

Do not add a Voxide-only backend route. `extraction.py` already says the client converts speech into `POST /api/v1/events` JSON.

### Capabilities to implement inside Voxide

These are voice-layer functions, not new HTTP endpoints. Arguments are the slot values. The HTTP body is always the event or query contract, with `business_id` and `language` added by the caller.

Shared arguments the caller adds, not the user:

- `business_id` — required on every call. Use the id the frontend already uses (`business_123` until auth exists).
- `language` — for `/events`, the interaction language (`en`, `am`, `om`, …). For `/query`, send `en` whenever `query` is English. Sending `am` or `om` makes `/query` reject the request.

#### `record_sale` — confirmation required

| Argument | Required | Maps to |
| --- | --- | --- |
| `item` | yes | `data.item` |
| `quantity` | yes | `data.quantity` |
| `amount` | yes | `data.amount` (line total) |
| `currency` | no | `data.currency` (omit to let the backend default ETB) |
| `customer` | no | `data.customer` |
| `date` | no | `data.date` as `YYYY-MM-DD` only |

`POST /api/v1/events` with `event_type: "sale"`.

#### `record_expense` — confirmation required

| Argument | Required | Maps to |
| --- | --- | --- |
| `description` | yes | `data.description` |
| `amount` | yes | `data.amount` |
| `currency` | no | `data.currency` |
| `category` | no | `data.category` |
| `date` | no | `data.date` |

`event_type: "expense"`.

#### `record_purchase` — confirmation required

| Argument | Required | Maps to |
| --- | --- | --- |
| `item` | yes | `data.item` |
| `quantity` | yes | `data.quantity` |
| `amount` | yes | `data.amount` |
| `currency` | no | `data.currency` |
| `supplier` | no | `data.supplier` |
| `date` | no | `data.date` |

`event_type: "purchase"`. Do not also send an expense for the same stock buy unless the user described a separate operating cost.

#### `adjust_inventory` — confirmation required

| Argument | Required | Maps to |
| --- | --- | --- |
| `item` | yes | `data.item` |
| `quantity` | yes | `data.quantity` (signed) |
| `reason` | yes | `data.reason` |
| `date` | no | `data.date` |

`event_type: "inventory_adjustment"`. “Two shirts were damaged” is `quantity: -2`, not a sale and not an expense.

#### `record_customer_debt` — confirmation required

| Argument | Required | Maps to |
| --- | --- | --- |
| `customer` | yes | `data.customer` |
| `amount` | yes | `data.amount` |
| `direction` | yes | `owed_to_business` or `owed_by_business` |
| `currency` | no | `data.currency` |
| `date` | no | `data.date` |

`event_type: "customer_debt"`.

Map speech before the POST:

- “Hana owes me 600” / “Hana took 600 on credit” → `owed_to_business`
- “I owe Hana 600” → `owed_by_business`

If the direction is unclear, ask. Do not default it.

#### `ask_business` — read-only, no confirmation

| Argument | Required | Maps to |
| --- | --- | --- |
| `query` | yes | English question string |

`POST /api/v1/query`.

Speak `message` on success. The structured `result` is what the UI can show; do not recompute it.

Useful question shapes the parser actually accepts:

- “How much did I sell today?”
- “How much did I sell this week?” / “this month?”
- “How many shirts did I sell?”
- “What did I spend this week?”
- “What’s the cost of my purchases?”
- “What were my biggest expenses this month?”
- “How many shirts do I have left?”
- “How much does Hana owe me?”
- “Who owes me money?”

#### `check_health` — optional, read-only

`GET /api/v1/health`. Not a user-facing voice command.

### Errors and clarification back to the user

| Backend outcome | Voice behavior |
| --- | --- |
| `201` / query `200`, `success: true` | Speak `message`. Do not invent a second summary that changes the numbers. |
| `400`, `status: "needs_clarification"` | Ask `message` in the user’s language. Keep already collected slots. `missing_fields` says what is still empty. After the user answers, POST again with the merged payload. |
| `400`, `error.code: "VALIDATION_ERROR"` | Speak `error.message`. Do not retry the same payload. The user has to change the value (amount not positive, bad direction, bad date, unsupported type). |
| Network / 5xx / the process does not start | Say the business service is unavailable. Do not store the event locally and replay it later without showing the user, or you will double-post once the server is back. |
| Query success with amount 0 | That is a real answer, not an error. Speak it. |

Clarification `message` and validation `message` are English. **Recommendation:** translate only the prompt you speak. Send the backend the original field values, not a translated rewrite of a name or item, unless the product has decided on one storage language (see constraints).

### Multilingual input

Implemented behavior:

- Event text is stored as sent. Amharic or Afaan Oromo item names, descriptions, and customer names are allowed. Validation does not translate them.
- Query understanding is English keywords only.
- `language` on `/query` must be English or the backend refuses before it looks at the text.
- Response `message` is always English.
- Customer-name capture in questions only matches a single Latin-script token.

**Recommendation for the voice layer:**

1. Run STT in the language the user is speaking (`en`, `am`, `om`).
2. For a question, produce an English `query` that uses the patterns above, and send `language: "en"`. Keep item and customer tokens identical to the strings previously stored, or the inventory/debt match will miss.
3. For a write, fill structured fields. Send `language` as the spoken language so the row records the interaction language. Do not put the whole sentence in `data`.
4. Do not expect this backend to parse Amharic grammar or to answer in Amharic. TTS language is Voxide’s job; you can speak a translation of `message`, but the numbers must stay the ones in `result`.

### What Voxide should not implement

- Stock math, sales totals, expense totals, purchase totals, debt nets
- Its own event database or a “pending ledger” that becomes truth
- A new public REST shape, agent-gateway payload, or JWT login
- Silent retries that POST `/events` again after a 201
- Guessing `direction`, `amount`, or `quantity` after the backend asked for clarification
- Treating a customer on a sale as a debt
- Recording a stock purchase as both `purchase` and `expense`
- Category-level expense answers, supplier payable lists, or advice — the backend does not support them
- Editing history

Pre-checks in the voice layer (missing amount, quantity zero) are fine as a faster prompt. The backend check is still mandatory.

---

## Frontend integration requirements

Compared with the frontend already implemented in the sibling project `Voice-first-buisness-assistant` (`src/lib/api/client.ts`, `src/lib/api/types.ts`, `src/lib/config.ts`, assistant workspace). That client is aligned with `docs/API_CONTRACT.md` and with the live handlers.

It already:

- `GET /api/v1/health`
- `POST /api/v1/events` with `business_id`, `language`, `event_type`, `data`
- `POST /api/v1/query` with `business_id`, `language`, `query`
- Treats `needs_clarification` / `NEEDS_CLARIFICATION` / `missing_fields` as clarification, and other failures as errors
- Sends `business_id: "business_123"` and `language: "en"`
- Builds the five event payloads with the same required fields the handlers enforce
- Does not send auth headers
- Does not calculate totals locally; it displays `message` and the JSON `result`

### Required frontend changes

None, for the contract. The request and success shapes the frontend parses (`success`, `event.id`, `event.event_type`, `event.data`, `message`, `query_type`, `result`) are still what the handlers return.

The frontend does not need a contract change for this repair.

### Changes that would be wrong

- Do not switch writes to `POST /api/v1/agent-gateway`. That route does not exist.
- Do not expect `event_id` instead of `event.id`.
- Do not expect `remaining_stock`.
- Do not add `Authorization: Bearer`.
- Do not split one event form into `/api/v1/sales`, `/expenses`, and so on. Those modules are empty files.
- Do not require new response fields. There are none on the live API.

### Optional later

- Surface `missing_fields` as highlighted form fields (the client already returns them).
- A voice panel that posts the same two functions after Voxide returns slots.
- Stop hard-coding `business_123` when a real identity exists. It does not exist yet.
- If queries are ever sent in Amharic, translate to English first. Sending `language: "am"` is an implemented backend rejection, not a frontend bug.

---

## Important constraints

- **Contract to code against:** `POST /api/v1/events`, `POST /api/v1/query`, `GET /api/v1/health`, bodies in this document. `docs/API_CONTRACT.md` and `README.md` agree.
- **Startup:** `app.main` imports. Routes stay on `/api/v1`. Do not add a second prefix.
- **Database:** one SQLite file, default `sqlite:///./data/app.db`, table `events` only. `created_at` is not the business date. `data.date` is.
- **No auth.** Anyone who can reach the port can read and write any `business_id`.
- **No idempotency key.**
- **Amounts** are line totals, not unit prices. No tax, no discount, no quantity × price check.
- **Currency** defaults to ETB. Any uppercase string is accepted. Mixed currencies in one query become ETB.
- **Dates** must be `YYYY-MM-DD` or omitted (server local today). Week starts Monday. No timezone field.
- **Inventory** may go negative. No reservation and no “cannot sell more than stock” rule.
- **Debt** is an append-only net. Same direction twice means two debts, not an edit.
- **Queries** are English-only. Item and customer matching is case-insensitive exact text. Customer questions only capture one Latin word.
- **Languages** on events are stored and ignored by logic. User-facing handler strings are English.
- **Unsupported:** update, delete, list endpoints, payments, auth, advice, category expense queries, supplier-payable queries, non-English query parsing, agent gateway.
- **Dependencies:** `requirements.txt` is FastAPI, uvicorn, SQLAlchemy, Pydantic v2, pydantic-settings, python-dotenv, pytest, httpx. No JWT library, no async SQLite driver, no LLM SDK.
- **Deployment assumptions in code:** `uvicorn app.main:app` or `python -m app`, host/port from `app.config`, CORS from `CORS_ORIGINS`. Live settings are `DATABASE_URL`, `HOST`, `PORT`, and `CORS_ORIGINS`.
- **Schema split:** live metadata is `app.db.Base` (`events` only). `Business`, `InventoryItem`, and `EventLog` use `app.models.base.RelationalBase` and are not created. Do not point `init_db` at them.
- **Tests** cover the live contract. 35 passed after the startup repair.

### Inconsistencies found

| Location | What it says | What the code does |
| --- | --- | --- |
| `README.md` before this repair | JWT, domain routes, `POST /api/v1/agent-gateway`, `remaining_stock` | README now matches the three live endpoints and `.env.example`. Those other routes are still not served. |
| `app/main.py` after PR #2 | Included the router again with `settings.API_V1_STR` and created tables on an async engine | Those lines were removed. One router, prefix `/api/v1`, sync `init_db`. |
| `app/api/v1/router.py` and `endpoints/agent_gateway.py` | Alternate `/events` and `/query` | Not mounted. Identical copies. Non-sale events are fake success. |
| `app/models/base.py` | Was a JWT copy, while models imported `AuditMixin` | Now `RelationalBase` and `AuditMixin`. Not used by `init_db`. |
| `app/core/security.py` | bcrypt + `jose` JWT | Not referenced by live routes. Packages are not in `requirements.txt`. |
| `app/core/errors.py` clarification | HTTP 200 | Live clarifications are HTTP 400. Handler is not attached. |
| `app/services/analytics_service.py` | “You sold X today” | Sums all sales and labels them as today. |
| `docs/API_CONTRACT.md` §13 | “Backend interprets request” for the whole NL flow | True for `/query` only. Events require structured `data`. |
| `docs/API_CONTRACT.md` §10 | Expenses by category, purchase history, inventory changes | Not implemented as query types. |
| Relational sketches | `businesses`, `inventory_items`, `event_logs` | Defined on `RelationalBase`. Live `create_all` still creates only `events`. `app.core.db` is still unused and its settings object still fails to construct. |

---

## Known limitations

- No user accounts. Single shared `business_id` string.
- English query parser only. No Amharic or Afaan Oromo understanding in the backend.
- English voice replies only, unless Voxide translates `message` without changing numbers.
- No confirmation API. Clients must confirm before they POST.
- No undo.
- No pagination or export.
- No unit price, margin, or profit endpoint. Profit is not sales minus expenses; those totals exist separately if a client asks both questions.
- “This week” depends on the server’s local date and Monday as the first day.
- Keyword collisions: a question that mentions both selling and spending is rejected rather than answered.
- Names with spaces or non-Latin characters can be **stored** on a debt event but cannot be **found** by “How much does X owe me?” because of the Latin one-word regex.
- Storing an item in Amharic and later asking “how many shirts” will not match.
- Empty endpoint files and `app/core/` are still in the tree. They are not mounted. The README says they are not part of the running API.

---

## Recommended next steps

These are recommendations. They are not work already done on `main`.

### 1. Backend — only what is necessary before other services

1. Startup is restored and the existing 35 tests passed. No further backend change is required before Voxide or the current frontend.
2. Leave `app/api/v1/router.py`, `agent_gateway.py`, and `app/core/` unmounted. `app.core.config.Settings()` still fails to construct, and `app.core.security` imports `passlib`, which is not installed.
3. Do not rewrite persistence onto `event_logs` / `inventory_items` for the hackathon. Those classes are sketches. They have no handlers on the live routes and would break the frontend contract.

No other backend change is required for Voxide or the current frontend to integrate.

### 2. Voxide

1. Implement the six functions above against `POST /api/v1/events` and `POST /api/v1/query` only.
2. Confirm every write with the user. Call queries immediately.
3. Translate questions into English keyword-style sentences; send `language: "en"` on `/query`.
4. On clarification, ask and retry once with merged slots. On `VALIDATION_ERROR`, stop and explain.
5. Speak `message`. Display or log `result` if a UI is attached. Do not recompute stock or money.

### 3. Frontend

1. Keep the existing client.
2. After the backend boots, point `NEXT_PUBLIC_API_URL` at it and exercise health, one sale, one clarification, and one English query.
3. Add a voice surface only as a caller of the same `createEvent` and `queryBusiness` functions. Do not add a second payload shape for Voxide.

### Order

1. Backend startup is repaired. Keep the event log.
2. Wire Voxide to the existing two POST endpoints, with confirmation on writes.
3. Point the existing frontend at the running API; add voice UI only as a thin caller of that same client.

Avoid a rewrite of the ledger, a new gateway, and auth until the voice path works on the event log that the tests already specify.
