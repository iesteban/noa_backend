from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_GRAPH_API = "https://graph.facebook.com/v19.0"
_POLL_INTERVAL = 10  # seconds between status checks
_POLL_TIMEOUT = 300  # seconds before giving up


# ---------------------------------------------------------------------------
# Template registry — add new templates here, nowhere else.
# ---------------------------------------------------------------------------

TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "appointment_request",
        "language": "es",
        "category": "UTILITY",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Hola {{1}}, {{2}} quiere organizarte una cita de {{3}}. "
                    "¿Qué días y horas te vienen bien?"
                ),
            }
        ],
    },
]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def _list_existing(
    client: httpx.AsyncClient, access_token: str, waba_id: str
) -> list[dict[str, Any]]:
    r = await client.get(
        f"{_GRAPH_API}/{waba_id}/message_templates",
        headers=_headers(access_token),
        params={"fields": "id,name,status,language,components", "limit": 200},
    )
    r.raise_for_status()
    return list(r.json().get("data", []))


async def _create(
    client: httpx.AsyncClient,
    access_token: str,
    waba_id: str,
    template: dict[str, Any],
) -> None:
    r = await client.post(
        f"{_GRAPH_API}/{waba_id}/message_templates",
        headers=_headers(access_token),
        json=template,
    )
    r.raise_for_status()
    logger.info("Created template %r (status: %s)", template["name"], r.json().get("status"))


async def _update(
    client: httpx.AsyncClient,
    access_token: str,
    template_id: str,
    name: str,
    components: list[dict[str, Any]],
) -> None:
    r = await client.post(
        f"{_GRAPH_API}/{template_id}",
        headers=_headers(access_token),
        json={"components": components},
    )
    r.raise_for_status()
    logger.info("Updated template %r — re-submitted for approval", name)


async def _poll_until_approved(
    client: httpx.AsyncClient,
    access_token: str,
    waba_id: str,
    names: list[str],
) -> None:
    pending = set(names)
    elapsed = 0
    while pending:
        if elapsed >= _POLL_TIMEOUT:
            raise TimeoutError(
                f"Timed out waiting for approval of templates: {', '.join(sorted(pending))}"
            )
        await asyncio.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL
        existing = await _list_existing(client, access_token, waba_id)
        by_name = {t["name"]: t for t in existing}
        for name in list(pending):
            status = by_name.get(name, {}).get("status", "UNKNOWN")
            if status == "APPROVED":
                logger.info("Template %r approved", name)
                pending.discard(name)
            elif status == "REJECTED":
                raise RuntimeError(f"Template {name!r} was rejected by Meta")
            else:
                logger.debug("Template %r status: %s (%ds elapsed)", name, status, elapsed)


# ---------------------------------------------------------------------------
# Content comparison
# ---------------------------------------------------------------------------


def _body_text(components: list[dict[str, Any]]) -> str:
    for c in components:
        if c.get("type", "").upper() == "BODY":
            return str(c.get("text", "")).strip()
    return ""


def _needs_update(defined: dict[str, Any], existing: dict[str, Any]) -> bool:
    return _body_text(defined["components"]) != _body_text(existing.get("components", []))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def sync_templates(access_token: str, waba_id: str) -> None:
    """Create or update all registered WhatsApp templates and wait for approval."""
    if not access_token or not waba_id:
        raise ValueError(
            "WHATSAPP_ACCESS_TOKEN and WHATSAPP_BUSINESS_ACCOUNT_ID must both be set"
        )

    async with httpx.AsyncClient(timeout=30) as client:
        existing = await _list_existing(client, access_token, waba_id)
        existing_by_name = {t["name"]: t for t in existing}

        pending: list[str] = []
        for template in TEMPLATES:
            name = template["name"]
            if name not in existing_by_name:
                logger.info("Template %r not found — creating", name)
                await _create(client, access_token, waba_id, template)
                pending.append(name)
            elif _needs_update(template, existing_by_name[name]):
                logger.info("Template %r content changed — updating", name)
                await _update(
                    client,
                    access_token,
                    existing_by_name[name]["id"],
                    name,
                    template["components"],
                )
                pending.append(name)
            else:
                status = existing_by_name[name].get("status", "UNKNOWN")
                if status != "APPROVED":
                    logger.warning("Template %r exists but status is %s", name, status)
                    pending.append(name)
                else:
                    logger.info("Template %r is up to date and approved — skipping", name)

        if pending:
            logger.info("Waiting for approval of: %s", ", ".join(pending))
            await _poll_until_approved(client, access_token, waba_id, pending)

    logger.info("All templates synced successfully")
