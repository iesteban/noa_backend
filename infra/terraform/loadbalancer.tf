resource "scaleway_lb_ip" "main" {
  count = var.enable_lb ? 1 : 0
  zone  = var.zone
}

resource "scaleway_lb" "main" {
  count = var.enable_lb ? 1 : 0
  name  = "noa-${var.environment}"
  ip_ids = [scaleway_lb_ip.main[0].id]
  type  = "LB-S"
  zone  = var.zone
}

data "dns_a_record_set" "container" {
  count = var.enable_lb ? 1 : 0
  host  = trimprefix(scaleway_container.api.domain_name, "https://")
}

resource "scaleway_lb_backend" "api" {
  count            = var.enable_lb ? 1 : 0
  lb_id            = scaleway_lb.main[0].id
  name             = "noa-api"
  forward_protocol = "tcp"
  forward_port     = 443

  server_ips = data.dns_a_record_set.container[0].addrs

  ssl_bridging = true

  health_check_https {
    uri         = "/health"
    method      = "GET"
    code        = 200
    host_header = trimprefix(scaleway_container.api.domain_name, "https://")
  }

  health_check_max_retries = 3
  health_check_timeout     = "3s"
  health_check_delay       = "10s"
}

resource "scaleway_lb_certificate" "main" {
  count = var.enable_lb && var.api_domain != "" ? 1 : 0
  lb_id = scaleway_lb.main[0].id
  name  = "noa-${var.environment}-cert"

  letsencrypt {
    common_name = var.api_domain
  }
}

resource "scaleway_lb_frontend" "https" {
  count        = var.enable_lb ? 1 : 0
  lb_id        = scaleway_lb.main[0].id
  backend_id   = scaleway_lb_backend.api[0].id
  name         = "https"
  inbound_port = 443

  certificate_ids = [for c in scaleway_lb_certificate.main : c.id]
}
