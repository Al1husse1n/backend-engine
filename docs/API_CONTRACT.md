# API Contract

## 1. Purpose

This document defines the API contract between the frontend, voice service (Voxide), and backend for the MVP.

The purpose is to ensure that all services agree on:

* what data is sent
* what data is returned
* which service owns each responsibility
* how business operations are represented
* how errors and ambiguous requests are handled

The API should remain small and focused on the MVP.

---

## 2. Service Responsibilities

### Frontend

Responsible for:

* User interface
* Text input
* Displaying responses
* Language selection
* Voice interaction UI
* Sending requests to the appropriate service

The frontend does not own business data or business rules.

### Voxide Service

Responsible for:

* Voice input
* Speech-to-text
* Voice output / text-to-speech
* Voice interaction flow
* Passing normalized user requests to the backend
* Returning backend responses through voice when appropriate

Voxide should not be the source of truth for business data.

### Backend

Responsible for:

* Request validation
* Interpreting/normalizing user intent
* Business operations
* Business rules
* Database access
* Persisting business data
* Retrieving business data
* Deterministic calculations
* Returning structured results

The backend/database is the source of truth for business state.

---

# 3. API Base

All backend API endpoints should use a versioned prefix:

`/api/v1`

The exact production domain is deployment-dependent.

---

# 4. Core API Operations

The MVP needs three core operations:

1. Record a business event
2. Query business information
3. Health check

The API should support natural-language interaction while keeping the resulting business operations structured and deterministic.

---

# 5. Record Business Event

## Endpoint

`POST /api/v1/events`

## Purpose

Records a business event after the user's natural-language request has been interpreted and validated.

Supported MVP event types:

* `sale`
* `expense`
* `purchase`
* `inventory_adjustment`
* `customer_debt`

The API should be designed so additional event types can be added later without redesigning the entire system.

---

## Request

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

### Required fields

| Field         | Type   | Description                       |
| ------------- | ------ | --------------------------------- |
| `business_id` | string | Identifies the business           |
| `language`    | string | Language used for the interaction |
| `event_type`  | string | Type of business event            |
| `data`        | object | Structured event information      |

The exact identity/authentication mechanism for `business_id` is an MVP implementation decision and must not be assumed to represent a full authentication system.

---

# 6. Event Data

## Sale

Example:

```json
{
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

Possible fields:

* `item`
* `quantity`
* `amount`
* `currency`
* `customer`
* `date`

---

## Expense

Example:

```json
{
  "event_type": "expense",
  "data": {
    "description": "transportation",
    "amount": 2000,
    "currency": "ETB",
    "category": "transportation",
    "date": "2026-09-17"
  }
}
```

Possible fields:

* `description`
* `amount`
* `currency`
* `category`
* `date`

---

## Purchase

Example:

```json
{
  "event_type": "purchase",
  "data": {
    "item": "shirts",
    "quantity": 20,
    "amount": 8000,
    "currency": "ETB",
    "supplier": null,
    "date": "2026-09-17"
  }
}
```

Possible fields:

* `item`
* `quantity`
* `amount`
* `currency`
* `supplier`
* `date`

---

## Inventory Adjustment

Example:

```json
{
  "event_type": "inventory_adjustment",
  "data": {
    "item": "shirts",
    "quantity": -2,
    "reason": "damaged",
    "date": "2026-09-17"
  }
}
```

A positive quantity increases inventory.

A negative quantity decreases inventory.

---

## Customer Debt

Example:

```json
{
  "event_type": "customer_debt",
  "data": {
    "customer": "Hana",
    "amount": 600,
    "currency": "ETB",
    "direction": "owed_to_business",
    "date": "2026-09-17"
  }
}
```

Possible fields:

* `customer`
* `amount`
* `currency`
* `direction`
* `date`

---

# 7. Event Response

## Success

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
      "date": "2026-09-17"
    }
  },
  "message": "Sale recorded successfully."
}
```

The backend response should contain enough structured information for the frontend or Voxide service to generate an appropriate user-facing response.

---

# 8. Ambiguous or Incomplete Requests

The system must not silently create incorrect business records.

If required information is missing or ambiguous, the backend should return a clarification response instead of creating the event.

Example:

```json
{
  "success": false,
  "status": "needs_clarification",
  "message": "What amount was the sale?",
  "missing_fields": [
    "amount"
  ]
}
```

The frontend/Voxide service can then ask the user for the missing information.

---

# 9. Query Business Information

## Endpoint

`POST /api/v1/query`

## Purpose

Allows the user to ask questions about their stored business information using natural language.

Examples:

* "How much did I sell today?"
* "What did I spend this week?"
* "How many shirts do I have left?"
* "Who owes me money?"
* "How much does Hana owe me?"
* "What were my biggest expenses this month?"

---

## Request

```json
{
  "business_id": "business_123",
  "language": "en",
  "query": "How much did I sell today?"
}
```

---

## Response

Example:

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

The `result` should contain structured data whenever possible.

The `message` is the user-facing representation of the verified result.

---

# 10. Query Types

The MVP should support a limited set of deterministic query types.

Examples:

### Sales

* total sales
* sales for a period
* sales of a specific item

### Expenses

* total expenses
* expenses for a period
* expenses by category

### Purchases

* purchase history
* total purchases
* purchases of a specific item

### Inventory

* current quantity
* inventory changes

### Customer Debt

* customers who owe money
* amount owed by a specific customer
* total outstanding debt

The exact query parser/LLM implementation is an implementation detail. The final result must come from the database and business logic rather than from an LLM's unsupported assumptions.

---

# 11. Health Check

## Endpoint

`GET /api/v1/health`

## Response

```json
{
  "status": "ok"
}
```

Used by the frontend, deployment platform, and team during integration/testing.

---

# 12. Error Format

Errors should use a consistent structure.

Example:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Amount must be greater than zero."
  }
}
```

Suggested error codes:

* `VALIDATION_ERROR`
* `NOT_FOUND`
* `INVALID_REQUEST`
* `NEEDS_CLARIFICATION`
* `INTERNAL_ERROR`

---

# 13. Natural Language Flow

The API is designed around the following flow:

```text
User speaks/types
        ↓
Voice service converts speech to text
        ↓
Natural-language request
        ↓
Backend interprets request
        ↓
Structured intent/data
        ↓
Validation
        ↓
Business logic
        ↓
Database
        ↓
Verified result
        ↓
Response
        ↓
Text and/or voice output
```

The LLM may assist with interpretation and response generation, but it must not become the source of truth for business state.

---

# 14. Multilingual Flow

Language should be treated as an interaction property rather than a business-logic dependency.

```text
Amharic / Oromo / English / other supported language
                    ↓
             User request
                    ↓
        Intent + structured data
                    ↓
       Language-independent logic
                    ↓
               Database
                    ↓
          Verified structured result
                    ↓
       Response in requested language
```

This allows additional languages to be added without rewriting the business logic.

---

# 15. Voice Integration

Voxide is responsible for voice-specific processing.

The backend should receive normalized information rather than depending on a particular voice provider's internal format.

For example, the backend should ultimately receive a request equivalent to:

```json
{
  "business_id": "business_123",
  "language": "en",
  "query": "How much did I sell today?"
}
```

rather than being tightly coupled to Voxide-specific audio-processing details.

The exact Voxide integration contract should be finalized by the person implementing the Voxide service.

---

# 16. Advice

The MVP may support basic business advice based only on information already stored in the database.

Example:

```text
User:
"Should I buy more stock?"

Backend:
- retrieves relevant inventory/sales data
- calculates relevant metrics
- produces a response based on available business data
```

External research and Scholarxiv integration are **not part of the MVP API**.

When Scholarxiv is added after the MVP, it should be integrated as an additional information/research capability rather than changing the core business-data API.

---

# 17. Source of Truth

The database is the source of truth for business state.

The following must not be treated as authoritative:

* LLM memory
* frontend state
* Voxide state
* generated text

For example:

```text
User:
"I sold three shirts for 900 ETB."

        ↓

LLM extracts:
sale
quantity = 3
amount = 900
item = shirts

        ↓

Backend validates

        ↓

Database records the sale

        ↓

Future query reads from database
```

---

# 18. MVP Non-Goals

The API does not need to support:

* full accounting
* advanced forecasting
* complex analytics
* external research retrieval
* Scholarxiv integration
* sophisticated recommendation systems
* large-scale automation
* every possible business operation

The contract should remain small enough for the team to implement within the hackathon.

---

# 19. Integration Rule

All three services must implement against this contract.

If an implementation requires changing:

* endpoint names
* request fields
* response fields
* event types
* ownership boundaries

the change should be discussed with the team and reflected in this document before dependent services are built around the old contract.

The API contract is the shared interface between the services.
