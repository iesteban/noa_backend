#!/usr/bin/env bash
# Usage: scripts/set_webhook.sh <ngrok-url>
# Example: scripts/set_webhook.sh https://xxxx.ngrok-free.app
set -euo pipefail

URL="${1:?Usage: set_webhook.sh <ngrok-url>}"

# Strip trailing slash if present
URL="${URL%/}"

# Load .env from repo root
ENV_FILE="$(dirname "$0")/../.env"
set -a; source "$ENV_FILE"; set +a

echo "Setting webhook → ${URL}/telegram"

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"${URL}/telegram\",
    \"secret_token\": \"${TELEGRAM_WEBHOOK_SECRET}\",
    \"allowed_updates\": [\"message\", \"edited_message\"]
  }" | python3 -m json.tool
