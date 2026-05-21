"""
Sync WhatsApp message templates with the Meta Graph API.

Usage:
    python -m app.scripts.sync_wa_templates

Reads WHATSAPP_ACCESS_TOKEN and WHATSAPP_BUSINESS_ACCOUNT_ID from the environment
(or from the .env file loaded by app.config).
"""

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from app.config import settings  # noqa: E402 — after basicConfig
from app.messaging.whatsapp_templates import sync_templates  # noqa: E402


def main() -> None:
    if not settings.whatsapp_business_account_id.strip():
        print("WHATSAPP_BUSINESS_ACCOUNT_ID is not set — nothing to do.")
        sys.exit(0)
    if not settings.whatsapp_access_token.strip():
        print("WHATSAPP_ACCESS_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(
        sync_templates(settings.whatsapp_access_token, settings.whatsapp_business_account_id)
    )


if __name__ == "__main__":
    main()
