# DNS records for botnoa.com — managed via Cloudflare.
#
# BEFORE the first apply: delete the two existing A records for botnoa.com
# in the Cloudflare dashboard (they point to old Cloudflare Anycast IPs).
# The www CNAME (→ botnoa.com) already exists and keeps working automatically.

resource "cloudflare_record" "landing_root" {
  zone_id = var.cloudflare_zone_id
  name    = "@"
  type    = "CNAME"
  value   = "${scaleway_object_bucket.www.name}.s3-website.${var.region}.scw.cloud"
  proxied = true
  ttl     = 1
}
