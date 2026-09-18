"""Natural-language extraction interface for recording events.

This backend does not include an LLM. Voice/frontend clients (or a future
extractor) should convert natural language into a structured event and then
call POST /api/v1/events.

Query questions are handled separately by the English-only keyword parser in
`app/services/query.py`. That parser maps text to a QueryIntent, then reads the
database. It does not persist, translate, or use an LLM.

Do not persist from this layer. Persistence happens only after validation.
"""

from typing import Any, Protocol


class EventExtractor(Protocol):
    def extract(
        self,
        *,
        business_id: str,
        language: str,
        text: str,
    ) -> dict[str, Any]:
        """Return a payload compatible with POST /api/v1/events.

        Expected shape:
        {
            "business_id": "...",
            "language": "...",
            "event_type": "sale" | "expense" | "purchase" | "inventory_adjustment" | "customer_debt",
            "data": { ... }
        }
        """
        ...
