variable "region" {
  description = "Scaleway region"
  type        = string
  default     = "fr-par"
}

variable "zone" {
  description = "Scaleway zone"
  type        = string
  default     = "fr-par-1"
}

variable "environment" {
  description = "Deployment environment (production, staging)"
  type        = string
  default     = "production"
}

variable "image_tag" {
  description = "Docker image tag to deploy (e.g. git SHA or semver)"
  type        = string
}

# --- Database ---

variable "db_node_type" {
  description = "RDB instance node type"
  type        = string
  default     = "DB-DEV-S"
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "noa"
}

variable "db_user" {
  description = "PostgreSQL user"
  type        = string
  default     = "noa"
}

variable "db_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
}

# --- Application secrets ---

variable "anthropic_api_key" {
  description = "Anthropic API key for Claude"
  type        = string
  sensitive   = true
}

variable "telegram_bot_token" {
  description = "Telegram bot token"
  type        = string
  sensitive   = true
}

variable "telegram_webhook_secret" {
  description = "Telegram webhook secret"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key for Whisper"
  type        = string
  sensitive   = true
}

variable "google_client_id" {
  description = "Google OAuth2 client ID for Calendar integration"
  type        = string
  sensitive   = true
}

variable "google_client_secret" {
  description = "Google OAuth2 client secret for Calendar integration"
  type        = string
  sensitive   = true
}

variable "google_redirect_uri" {
  description = "Google OAuth2 redirect URI for Calendar integration"
  type        = string
}

variable "sentry_dsn" {
  description = "Sentry DSN for error tracking (leave empty to disable)"
  type        = string
  sensitive   = true
  default     = ""
}

# --- Optional: load balancer ---

variable "cloudflare_api_token" {
  description = "Cloudflare API token — Zone:DNS:Edit permission for botnoa.com"
  type        = string
  sensitive   = true
}

variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for botnoa.com (Cloudflare dashboard → right sidebar)"
  type        = string
}

variable "enable_lb" {
  description = "Whether to deploy a load balancer (static IP, custom domain). Disable in dev to save ~€15/month."
  type        = bool
  default     = true
}

# --- Database ACL ---

variable "dev_machine_ip" {
  description = "IP address of the developer machine allowed to connect to the DB directly (for running migrations)"
  type        = string
  default     = ""
}

# --- Optional: custom domain ---

variable "api_domain" {
  description = "Custom domain for the API (e.g. api.noa.app). Leave empty to use the Scaleway-assigned URL."
  type        = string
  default     = ""
}
