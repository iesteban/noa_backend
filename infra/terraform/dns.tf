# DNS records for botnoa.com — managed via Cloudflare.
# Cloudflare is DNS-only (proxied = false); TLS is handled by Scaleway Edge Services.

resource "cloudflare_record" "landing_root" {
  zone_id = var.cloudflare_zone_id
  name    = "@"
  type    = "CNAME"
  content = scaleway_edge_services_dns_stage.landing.default_fqdn
  proxied = false
  ttl     = 60
}
