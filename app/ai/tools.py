from __future__ import annotations

from typing import Any

# Tool schema dicts consumed directly by the Anthropic SDK.
# cache_control is placed on the LAST tool in each list (Layer 2 cache breakpoint).

_CONTRACTOR_TOOL_LIST: list[dict[str, Any]] = [
    {
        "name": "search_client",
        "description": (
            "Search the contractor's clients by name. "
            "Returns a list of matches for disambiguation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Partial or full client name to search for.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "log_job",
        "description": "Log a completed job and save it to the database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "UUID of the client (from search_client).",
                },
                "description": {
                    "type": "string",
                    "description": "What was done.",
                },
                "date": {
                    "type": "string",
                    "description": "Date of work in YYYY-MM-DD format.",
                },
                "duration_hours": {
                    "type": "number",
                    "description": "Hours worked (optional).",
                },
                "amount": {
                    "type": "number",
                    "description": "Amount to charge in euros (before tax).",
                },
            },
            "required": ["client_id", "description", "date", "amount"],
        },
    },
    {
        "name": "create_invoice",
        "description": (
            "Generate a legal SII-compatible PDF invoice for a client. "
            "Returns the PDF URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "UUID of the client."},
                "job_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "UUIDs of jobs to include as invoice lines.",
                },
                "date": {"type": "string", "description": "Invoice issue date (YYYY-MM-DD)."},
                "due_date": {
                    "type": "string",
                    "description": "Payment due date (YYYY-MM-DD). Optional.",
                },
            },
            "required": ["client_id", "job_ids", "date"],
        },
    },
    {
        "name": "create_budget",
        "description": "Generate a budget (presupuesto) PDF and return its URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number"},
                        },
                        "required": ["description", "quantity", "unit_price"],
                    },
                    "description": "Line items for the budget.",
                },
                "valid_until": {
                    "type": "string",
                    "description": "Expiry date (YYYY-MM-DD). Optional.",
                },
            },
            "required": ["client_id", "lines"],
        },
    },
    {
        "name": "get_client_history",
        "description": "Return jobs, invoices, and payments for a client within a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)."},
                "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)."},
            },
            "required": ["client_id"],
        },
    },
    {
        "name": "get_unpaid_invoices",
        "description": "Return unpaid invoices, optionally filtered to a single client.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "UUID of the client to filter by. Optional.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_availability",
        "description": "Return free calendar slots between two dates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)."},
                "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)."},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "create_appointment",
        "description": "Create an appointment and add it to the contractor's calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "UUID of the client. Optional."},
                "starts_at": {
                    "type": "string",
                    "description": "Start datetime in ISO 8601 format.",
                },
                "duration_minutes": {"type": "integer"},
                "description": {"type": "string"},
            },
            "required": ["starts_at", "duration_minutes", "description"],
        },
    },
    {
        "name": "send_payment_reminder",
        "description": "Send a payment reminder to a client for an overdue invoice.",
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string", "description": "UUID of the invoice."},
            },
            "required": ["invoice_id"],
        },
    },
    {
        "name": "get_tax_summary",
        "description": "Return income and expense summary for a quarter (for modelo 303/130).",
        "input_schema": {
            "type": "object",
            "properties": {
                "quarter": {
                    "type": "integer",
                    "description": "Quarter number (1–4).",
                    "enum": [1, 2, 3, 4],
                },
                "year": {"type": "integer", "description": "Four-digit year."},
            },
            "required": ["quarter", "year"],
        },
    },
    {
        "name": "send_file_to_client",
        "description": "Forward a PDF (invoice or budget) to a client's chat.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "file_url": {"type": "string", "description": "Storage URL of the PDF."},
                "message": {
                    "type": "string",
                    "description": "Accompanying text message. Optional.",
                },
            },
            "required": ["client_id", "file_url"],
        },
    },
]

_CLIENT_TOOL_LIST: list[dict[str, Any]] = [
    {
        "name": "get_contractor_availability",
        "description": "Return the contractor's free calendar slots between two dates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)."},
                "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)."},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "book_appointment",
        "description": "Book an appointment with the contractor and notify them.",
        "input_schema": {
            "type": "object",
            "properties": {
                "starts_at": {
                    "type": "string",
                    "description": "Start datetime in ISO 8601 format.",
                },
                "description": {"type": "string", "description": "Reason for the appointment."},
            },
            "required": ["starts_at", "description"],
        },
    },
    {
        "name": "get_my_invoices",
        "description": "Return this client's invoices with the contractor.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_payment_info",
        "description": "Return the contractor's IBAN and Bizum number for payment.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "notify_contractor",
        "description": (
            "Escalate to the contractor — sends them a message in their own chat. "
            "Use when a client question cannot be resolved with other tools."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The client's question or issue to relay.",
                },
            },
            "required": ["message"],
        },
    },
]


def _with_cache(tool_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the list with cache_control added to the last tool (Layer 2 breakpoint)."""
    if not tool_list:
        return tool_list
    return [
        *tool_list[:-1],
        {**tool_list[-1], "cache_control": {"type": "ephemeral"}},
    ]


CONTRACTOR_TOOLS: list[dict[str, Any]] = _with_cache(_CONTRACTOR_TOOL_LIST)
CLIENT_TOOLS: list[dict[str, Any]] = _with_cache(_CLIENT_TOOL_LIST)
