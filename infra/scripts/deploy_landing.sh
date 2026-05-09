#!/usr/bin/env bash
# Sync the landing/ directory to the noa-www S3 bucket.
#
# Usage:
#   source .env.production
#   ./infra/scripts/deploy_landing.sh
#
# Requires: SCW_ACCESS_KEY and SCW_SECRET_KEY in the environment (source .env.production).
# Uses boto3 from the project venv — no aws CLI needed.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

if [[ -z "${SCW_ACCESS_KEY:-}" || -z "${SCW_SECRET_KEY:-}" ]]; then
  echo "Error: SCW_ACCESS_KEY and SCW_SECRET_KEY must be set."
  echo "       Run: source .env.production"
  exit 1
fi

REPO_ROOT="$REPO_ROOT" "$REPO_ROOT/.venv/bin/python" - <<'PYEOF'
import os, mimetypes, pathlib, boto3

BUCKET   = "noa-www"
ENDPOINT = "https://s3.fr-par.scw.cloud"
REGION   = "fr-par"
LANDING  = pathlib.Path(os.environ["REPO_ROOT"]) / "landing"

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    region_name=REGION,
    aws_access_key_id=os.environ["SCW_ACCESS_KEY"],
    aws_secret_access_key=os.environ["SCW_SECRET_KEY"],
)

# Configure static website hosting
print("==> Configuring static website hosting...")
s3.put_bucket_website(
    Bucket=BUCKET,
    WebsiteConfiguration={
        "IndexDocument": {"Suffix": "index.html"},
        "ErrorDocument": {"Key": "404.html"},
    },
)

# Upload all files in landing/
existing = {obj["Key"] for obj in s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])}
uploaded = set()

for path in sorted(LANDING.rglob("*")):
    if not path.is_file():
        continue
    key = str(path.relative_to(LANDING))
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "application/octet-stream"
    print(f"    upload: {key} ({mime})")
    s3.upload_file(
        str(path),
        BUCKET,
        key,
        ExtraArgs={
            "ACL": "public-read",
            "ContentType": mime,
            "CacheControl": "max-age=3600, public",
        },
    )
    uploaded.add(key)

# Remove stale files
for key in existing - uploaded:
    print(f"    delete: {key}")
    s3.delete_object(Bucket=BUCKET, Key=key)

print(f"\n==> Deploy complete.")
print(f"    URL: https://botnoa.com")
PYEOF
