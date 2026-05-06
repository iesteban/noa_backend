locals {
  image = "${scaleway_registry_namespace.main.endpoint}/noa-api:${var.image_tag}"

  # asyncpg connection string built from RDB outputs.
  # urlencode() the password so special characters (@, &, etc.) don't break URL parsing.
  database_url = "postgresql+asyncpg://${var.db_user}:${urlencode(var.db_password)}@${scaleway_rdb_instance.main.load_balancer[0].ip}:${scaleway_rdb_instance.main.load_balancer[0].port}/${var.db_name}"
}

resource "scaleway_container_namespace" "main" {
  name        = "noa-${var.environment}"
  region      = var.region
  description = "Noa API — ${var.environment}"
}

resource "scaleway_container" "api" {
  namespace_id = scaleway_container_namespace.main.id
  name         = "noa-api"
  region       = var.region

  registry_image = local.image
  port           = 8000
  cpu_limit      = 1120   # milli-vCPU
  memory_limit   = 1120   # MB (must match cpu_limit in milli-vCPU)

  min_scale = 1   # keep one instance warm — eliminates cold starts for webhooks
  max_scale = 5

  # The container is accessible through the load balancer only.
  privacy = "public"

  # Health check path (FastAPI exposes /health).
  http_option = "enabled"

  environment_variables = {
    ENVIRONMENT = var.environment
    LOG_LEVEL   = "INFO"
    SCW_REGION  = var.region
    SCW_BUCKET  = scaleway_object_bucket.app.name
  }

  secret_environment_variables = {
    DATABASE_URL            = local.database_url
    ANTHROPIC_API_KEY       = var.anthropic_api_key
    TELEGRAM_BOT_TOKEN      = var.telegram_bot_token
    TELEGRAM_WEBHOOK_SECRET = var.telegram_webhook_secret
    OPENAI_API_KEY          = var.openai_api_key
    SCW_ACCESS_KEY          = scaleway_iam_api_key.api.access_key
    SCW_SECRET_KEY          = scaleway_iam_api_key.api.secret_key
    GOOGLE_CLIENT_ID        = var.google_client_id
    GOOGLE_CLIENT_SECRET    = var.google_client_secret
    GOOGLE_REDIRECT_URI     = var.google_redirect_uri
  }

  depends_on = [
    scaleway_rdb_privilege.noa,
    scaleway_iam_policy.bucket_readwrite,
  ]
}

# Optional: bind a custom domain to the container (used when no LB is needed).
resource "scaleway_container_domain" "api" {
  count        = var.api_domain != "" ? 1 : 0
  container_id = scaleway_container.api.id
  hostname     = var.api_domain
  region       = var.region
}
