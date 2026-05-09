# Scaleway Edge Services CDN for botnoa.com landing page.
# Chain: DNS stage → TLS stage (managed cert) → backend stage (S3 website bucket).

resource "scaleway_edge_services_plan" "landing" {
  name = "starter"
}

resource "scaleway_edge_services_pipeline" "landing" {
  depends_on = [scaleway_edge_services_plan.landing]
  name        = "noa-landing"
  description = "Landing page CDN for botnoa.com"
}

resource "scaleway_edge_services_backend_stage" "landing" {
  pipeline_id = scaleway_edge_services_pipeline.landing.id

  s3_backend_config {
    bucket_name   = scaleway_object_bucket.www.name
    bucket_region = var.region
    is_website    = true
  }
}

resource "scaleway_edge_services_tls_stage" "landing" {
  pipeline_id         = scaleway_edge_services_pipeline.landing.id
  managed_certificate = true
  backend_stage_id    = scaleway_edge_services_backend_stage.landing.id
}

resource "scaleway_edge_services_dns_stage" "landing" {
  pipeline_id  = scaleway_edge_services_pipeline.landing.id
  fqdns        = ["botnoa.com", "www.botnoa.com"]
  tls_stage_id = scaleway_edge_services_tls_stage.landing.id
}

resource "scaleway_edge_services_head_stage" "landing" {
  pipeline_id   = scaleway_edge_services_pipeline.landing.id
  head_stage_id = scaleway_edge_services_dns_stage.landing.id
}
