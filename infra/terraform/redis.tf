resource "scaleway_redis_cluster" "main" {
  name         = "noa-${var.environment}"
  version      = "7"
  node_type    = var.redis_node_type
  user_name    = "noa"
  password     = var.redis_password
  cluster_size = 1
  zone         = var.zone
  tls_enabled  = true

  public_network {}
}
