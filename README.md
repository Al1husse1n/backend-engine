# backend-engine

Backend service for the STARK Hackathon 2026 Voice-First Business Assistant.

This API is the **source of truth** for business state. Clients send structured HTTP requests. The backend validates them, applies deterministic event handling, and persists accepted events.

Speech-to-text and text-to-speech are out of scope for this service. Recording events is structured JSON. `POST /api/v1/query` includes limited deterministic **English keyword** interpretation for the MVP. It is not general-purpose natural-language understanding, does not use an LLM, and returns clarification when the question is unsupported or ambiguous.

The shared request/response contract lives in [docs/API_CONTRACT.md](docs/API_CONTRACT.md). Integration notes for the frontend and Voxide live in [docs/CROSS_SERVICE_INTEGRATION.md](docs/CROSS_SERVICE_INTEGRATION.md). This README does not replace those documents.

## Stack

- Python 3.11+
- FastAPI
- SQLAlchemy 2
- SQLite by default
- Pydantic v2

There is no authentication system and no LLM integration in this repository.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive API.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy database URL |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Bind port |
| `CORS_ORIGINS` | `*` | Browser origins. `*` allows any origin **without** credentials. For production, set an explicit comma-separated list such as `http://localhost:3000,https://your-frontend.example` (credentials enabled only when origins are explicit). |

Copy `.env.example` to `.env`. Do not commit secrets. This MVP does not require API keys.

## Implemented endpoints

- `POST /api/v1/events` — record a structured business event
- `POST /api/v1/query` — ask about stored business state
- `GET /api/v1/health` — liveness check

Supported event types: `sale`, `expense`, `purchase`, `inventory_adjustment`, `customer_debt`.

### Example request

```bash
curl -X POST http://localhost:8000/api/v1/events ^
  -H "Content-Type: application/json" ^
  -d "{\"business_id\":\"business_123\",\"language\":\"en\",\"event_type\":\"sale\",\"data\":{\"item\":\"shirts\",\"quantity\":3,\"amount\":900,\"currency\":\"ETB\",\"customer\":null,\"date\":\"2026-09-17\"}}"
```

### Example success response

`201 Created`

```json
{
  "success": true,
  "event": {
    "id": "event_123",
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

Incomplete events return `needs_clarification`. Invalid values return `VALIDATION_ERROR`. Nothing is written until validation succeeds.

### Example query

```bash
curl -X POST http://localhost:8000/api/v1/query ^
  -H "Content-Type: application/json" ^
  -d "{\"business_id\":\"business_123\",\"language\":\"en\",\"query\":\"How much did I sell today?\"}"
```

Example success response:

```json
{
  "success": true,
  "query_type": "sales_total",
  "result": {
    "amount": 4500,
    "currency": "ETB",
    "period": {
      "start": "2026-09-17",
      "end": "2026-09-17"
    }
  },
  "message": "You sold 4,500 ETB today."
}
```

Query answers are computed from persisted events after the text is mapped to a structured `QueryIntent`. The parser is a small English keyword/regex matcher (no LLM). Ambiguous or non-English questions return `needs_clarification` instead of a guessed total.

## Tests

```bash
python -m pytest
```

## MVP assumptions

- `business_id` is a client-supplied identifier, not an authenticated user. There is no login, signup, or tenant isolation beyond storing the provided ID on each event. The backend does not hard-code a demo business.
- If `currency` is omitted on an event, it defaults to `ETB`. This is an MVP convenience, not a multi-currency system.
- If `date` is omitted on an event, it defaults to the **server's current local calendar date** (`YYYY-MM-DD`). Query phrases such as "today" / "this week" / "this month" use that same server date. Timezones are **not** implemented; aligning the server clock (or passing dates from the client) is a future integration concern.
- Inventory on hand is calculated at query time from the event log, with **case-insensitive, whitespace-normalized** item matching:
  - `purchase`: +quantity
  - `sale`: −quantity
  - `inventory_adjustment`: +signed quantity
  There is no separate inventory table in the live database. Item names that are also parser keywords (for example `today`, `left`, `cost`) are not treated as product names.
- A sale does not create a customer debt. A purchase does not create an expense. Debt is derived only from `customer_debt` events.
- Query interpretation is **English-only**. The `language` field is stored and accepted, but Amharic/Oromo (and other non-English values) are not parsed. Those requests return clarification rather than a guessed answer. `app/services/extraction.py` remains a placeholder for a later recording-side extractor. Multilingual NLP is out of scope.

## Architecture

```text
HTTP request
  → validation
  → event handler or query engine
  → append-only events table
  → structured response
```

New event types can be added by registering a handler. They do not need a new HTTP resource.

## Not part of the running API

Some files from an unfinished follow-up are still in the tree. They are not mounted and are not a second API:

- Empty modules under `app/api/v1/endpoints/` (`auth`, `users`, `sales`, `expenses`, and the other domain files) and `app/api/v1/router.py`.
- `app/core/` (async engine, JWT helpers). Those modules are not imported by `app.main`, and the security helper depends on packages that are not in `requirements.txt`.
- `Business`, `InventoryItem`, and `EventLog` in `app/models/`. They sit on `RelationalBase`. `init_db()` creates only the `events` table.

There is no `POST /api/v1/agent-gateway` route.
