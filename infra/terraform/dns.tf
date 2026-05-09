# DNS records for botnoa.com — managed via Cloudflare.
# Cloudflare is DNS-only (proxied = false); TLS is handled by Scaleway.

resource "cloudflare_record" "landing_root" {
  zone_id = var.cloudflare_zone_id
  name    = "@"
  type    = "CNAME"
  content = scaleway_edge_services_dns_stage.landing.default_fqdn
  proxied = false
  ttl     = 60
}

# api.botnoa.com (production) or api-staging.botnoa.com (staging)
resource "cloudflare_record" "api" {
  count   = var.api_domain != "" ? 1 : 0
  zone_id = var.cloudflare_zone_id
  name    = split(".", var.api_domain)[0]  # "api" or "api-staging"
  type    = "CNAME"
  content = scaleway_container.api.domain_name
  proxied = false
  ttl     = 60
}
