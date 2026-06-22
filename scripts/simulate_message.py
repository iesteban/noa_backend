#!/usr/bin/env python3

"""
Simulate an inbound bot message against the local dev server.

Usage:
    python scripts/simulate_message.py --message "Hola"
    python scripts/simulate_message.py --message "Hola" --channel whatsapp
    python scripts/simulate_message.py --message "Hola" --phone 34611223344
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import time
import urllib.request
from pathlib import Path

# Change to a phone registered as a contractor or client in your dev DB.
DEFAULT_PHONE = "34600000001"


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _telegram_payload(phone: str, message: str, update_id: int) -> dict:
    # Telegram identifies senders by chat_id (integer), not phone.
    # For dev purposes, derive a stable fake chat_id from the phone digits.
    chat_id = int("".join(c for c in phone if c.isdigit()) or "0") % (10**9)
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {
                "id": chat_id,
                "first_name": "Dev",
                "username": "dev_user",
            },
            "chat": {"id": chat_id, "type": "private"},
            "date": int(time.time()),
            "text": message,
        },
    }


def _whatsapp_payload(phone: str, message: str, update_id: int) -> dict:
    msg_id = f"wamid.dev{update_id:06d}"
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "dev-entry",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "id": msg_id,
                                    "from": phone,
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": message},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _hmac_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a bot webhook message locally.")
    parser.add_argument("--phone", default=DEFAULT_PHONE, help="Sender phone (digits only).")
    parser.add_argument("--message", required=True, help="Text message to send")
    parser.add_argument("--channel", choices=["telegram", "whatsapp"], default="telegram")
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--update-id", type=int, default=int(time.time()) % 100000)
    args = parser.parse_args()

    env = _load_env(Path(".env"))

    if args.channel == "telegram":
        payload = _telegram_payload(args.phone, args.message, args.update_id)
        body = json.dumps(payload).encode()
        secret = env.get("TELEGRAM_WEBHOOK_SECRET", "")
        url = f"{args.host}/telegram"
        headers = {
            "Content-Type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": secret,
        }
    else:
        payload = _whatsapp_payload(args.phone, args.message, args.update_id)
        body = json.dumps(payload).encode()
        app_secret = env.get("WHATSAPP_APP_SECRET", "")
        url = f"{args.host}/whatsapp"
        headers = {"Content-Type": "application/json"}
        if app_secret:
            headers["X-Hub-Signature-256"] = _hmac_signature(app_secret, body)

    print(f"POST {url}")
    print(f"Phone : {args.phone}")
    print(f"Message: {args.message}")
    print()

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"HTTP {resp.status}")
            print(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}", file=sys.stderr)
        print(exc.read().decode(), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
