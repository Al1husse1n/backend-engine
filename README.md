Here is the updated `README.md` reflecting the new modular architecture, multi-tenancy, authentication, domain services, and integration capabilities.

---

```markdown
# backend-engine

Backend service for the STARK Hackathon 2026 Voice-First Business Assistant.

This API is the **deterministic source of truth** for business state and multi-tenant ledger management. It receives structured HTTP/JSON requests from client interfaces (web/mobile) and the **AI Engine** (`voxide` + `scholararchive`), validates business constraints, executes atomic domain operations, and persists accepted events.

> **Note on Service Boundaries:** Speech-to-Text (STT), Text-to-Speech (TTS), and Large Language Model (LLM) intent parsing are explicitly **out of scope** for this repository. Natural language processing is handled externally by the `ai-engine` service, which emits normalized JSON payloads directly to this backend's execution endpoints.

---

## Architecture & Project Structure

The codebase is organized into domain-driven layers to ensure clear separation of concerns, scalability, and ease of testing.

```text
app/
├── api/
│   └── v1/
│       ├── endpoints/         # FastAPI route handlers
│       │   ├── auth.py          # Signup, Login, JWT issuing
│       │   ├── users.py         # User profiles & permissions
│       │   ├── business.py      # Multi-tenant business profiles
│       │   ├── sales.py         # Sales event creation & retrieval
│       │   ├── expenses.py      # Expense event logging
│       │   ├── purchases.py     # Stock acquisition
│       │   ├── inventory.py     # Current stock state & adjustments
│       │   ├── debts.py         # Customer debt balances & tracking
│       │   ├── analytics.py     # Calculated metrics (Totals, Margins)
│       │   ├── payments.py      # Subscriptions & payment webhooks
│       │   └── agent_gateway.py # High-speed execution gateway for AI Engine
│       ├── dependencies.py    # Auth guards, DB sessions, Tenant context
│       └── router.py          # Consolidated API Router
├── core/                      # System configuration & setup
│   ├── config.py              # Environment variables & Settings
│   ├── db.py                  # SQLAlchemy async session factory & engine
│   ├── security.py            # Password hashing (bcrypt) & JWT management
│   └── errors.py              # Global exception handlers
├── models/                    # SQLAlchemy Database Models (PostgreSQL/SQLite)
│   ├── base.py                # Base class & audit mixins
│   ├── user.py                # User & Role models
│   ├── business.py            # Multi-tenant business boundary
│   ├── ledger.py              # Sales, Expenses, Purchases, Customer Debts
│   ├── inventory.py           # Products & Stock records
│   └── payment.py             # Subscription logs
├── schemas/                   # Pydantic v2 Models (Request/Response validation)
│   ├── auth.py
│   ├── user.py
│   ├── business.py
│   ├── ledger.py
│   ├── inventory.py
│   └── agent_event.py         # Schemas for incoming AI Engine JSON events
└── services/                  # Deterministic Business Logic Execution
    ├── events/
    │   ├── sale_service.py    # Sales processing & atomic stock updates
    │   ├── expense_service.py # Expense logging
    │   ├── purchase_service.py# Inventory acquisition
    │   └── debt_service.py   # Customer credit & repayment tracking
    ├── analytics_service.py   # Deterministic calculations (Totals, Balances)
    └── payment_service.py     # Subscription logic

```

---

## Tech Stack

* **Python 3.11+**
* **FastAPI** — High-performance web framework
* **SQLAlchemy 2.0** — Async ORM & Database abstraction
* **Pydantic v2** — Data validation & settings management
* **PostgreSQL / SQLite** — Relational database persistence
* **Passlib & PyJWT** — Password hashing and JWT authentication

---

## Environment Variables

Copy `.env.example` to `.env` before running the application:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` | SQLAlchemy Async Database URL |
| `SECRET_KEY` | `your-super-secret-jwt-key` | Secret key used for signing JWT tokens |
| `ALGORITHM` | `HS256` | JWT encoding algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Token expiration time in minutes |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Bind port |
| `CORS_ORIGINS` | `*` | Allowed browser origins |

---

## Setup & Local Execution

### 1. Activate Virtual Environment

```bash
# macOS / Linux
source venv/bin/activate

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

```

### 2. Install Dependencies

```bash
pip install -r requirements.txt

```

### 3. Run Development Server

```bash
uvicorn app.main:app --reload --port 8000

```

Open [http://localhost:8000/docs](http://localhost:8000/docs?utm_source=gemini) for interactive Swagger documentation.

---

## API & Gateway Usage

### AI Engine Gateway (`POST /api/v1/agent-gateway`)

This endpoint is optimized for high-speed execution calls coming from the `ai-engine` service after processing voice input.

#### Example Event Payload:

```json
{
  "business_id": "bus_987654",
  "event_type": "sale",
  "data": {
    "item": "shirts",
    "quantity": 3,
    "amount": 900,
    "currency": "ETB",
    "customer": "Abebe",
    "date": "2026-09-20"
  }
}

```

#### Example Success Response (`201 Created`):

```json
{
  "success": true,
  "event_id": "evt_12345",
  "event_type": "sale",
  "message": "Sale recorded successfully: 3 shirts for 900 ETB to Abebe.",
  "data": {
    "remaining_stock": 17
  }
}

```

---

## Core MVP Principles

1. **Deterministic Execution:** Business metrics, stock deltas, and revenue totals are strictly calculated via code and SQL queries—never guessed or calculated by an LLM.
2. **Multi-Tenant Data Isolation:** All financial and operational records are bound to a verified `business_id`.
3. **Database as Single Source of Truth:** Unvalidated or ambiguous operations are rejected before writing to the database.

---

## Running Tests

```bash
python -m pytest

```

```

```