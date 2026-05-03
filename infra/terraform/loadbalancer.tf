# Static public IP — stable across redeployments, used for DNS A record.
resource "scaleway_lb_ip" "main" {
  zone = var.zone
}

resource "scaleway_lb" "main" {
  name = "noa-${var.environment}"
  ip_id = scaleway_lb_ip.main.id
  type  = "LB-S"
  zone  = var.zone
}

# Resolve the container's hostname to IPs so the LB backend can reach it.
# Scaleway Serverless Containers expose a stable HTTPS subdomain; the IP set
# behind it can change. The dns_a_record_set is re-evaluated on each apply,
# keeping the backend IPs current.
data "dns_a_record_set" "container" {
  host = trimprefix(scaleway_container.api.domain_name, "https://")
}

resource "scaleway_lb_backend" "api" {
  lb_id            = scaleway_lb.main.id
  name             = "noa-api"
  forward_protocol = "tcp"
  forward_port     = 443

  # IPs resolved from the container's managed HTTPS endpoint.
  server_ips = data.dns_a_record_set.container.addrs

  # SNI header so the container's TLS certificate matches.
  ssl_bridging = true

  health_check_https {
    uri              = "/health"
    method           = "GET"
    code             = 200
    host_header      = trimprefix(scaleway_container.api.domain_name, "https://")
  }

  health_check_max_retries = 3
  health_check_timeout     = "3s"
  health_check_delay       = "10s"
}

# HTTPS frontend — terminate TLS at the LB, issue a managed Let's Encrypt cert.
resource "scaleway_lb_certificate" "main" {
  count = var.api_domain != "" ? 1 : 0
  lb_id = scaleway_lb.main.id
  name  = "noa-${var.environment}-cert"

  letsencrypt {
    common_name = var.api_domain
  }
}

resource "scaleway_lb_frontend" "https" {
  lb_id        = scaleway_lb.main.id
  backend_id   = scaleway_lb_backend.api.id
  name         = "https"
  inbound_port = 443

  certificate_ids = [for c in scaleway_lb_certificate.main : c.id]
}

