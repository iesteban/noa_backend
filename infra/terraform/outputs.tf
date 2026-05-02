output "lb_ip" {
  description = "Public IP of the load balancer — point your DNS A record here"
  value       = scaleway_lb_ip.main.ip_address
}

output "container_url" {
  description = "Scaleway-assigned HTTPS URL of the API container"
  value       = scaleway_container.api.domain_name
}

output "registry_endpoint" {
  description = "Container registry endpoint (use as docker login host)"
  value       = scaleway_registry_namespace.main.endpoint
}

output "db_host" {
  description = "PostgreSQL host"
  value       = scaleway_rdb_instance.main.endpoint_ip
}

output "db_port" {
  description = "PostgreSQL port"
  value       = scaleway_rdb_instance.main.endpoint_port
}

output "bucket_name" {
  description = "Object storage bucket name"
  value       = scaleway_object_bucket.app.name
}

output "database_url" {
  description = "Full asyncpg connection string for the API"
  value       = local.database_url
  sensitive   = true
}
