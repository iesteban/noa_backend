resource "scaleway_registry_namespace" "main" {
  name       = "noa-${var.environment}"
  region     = var.region
  is_public  = false
}
