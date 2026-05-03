resource "scaleway_rdb_instance" "main" {
  name           = "noa-${var.environment}"
  node_type      = var.db_node_type
  engine         = "PostgreSQL-16"
  is_ha_cluster  = false        # enable in production when budget allows
  disable_backup = false
  backup_schedule_frequency   = 24
  backup_schedule_retention   = 7
  region         = var.region

  # Volume auto-grows up to 50 GB.
  volume_type       = "sbs_5k"
  volume_size_in_gb = 5
}

resource "scaleway_rdb_database" "noa" {
  instance_id = scaleway_rdb_instance.main.id
  name        = var.db_name
  region      = var.region
}

resource "scaleway_rdb_user" "noa" {
  instance_id = scaleway_rdb_instance.main.id
  name        = var.db_user
  password    = var.db_password
  is_admin    = false
  region      = var.region

  lifecycle {
    ignore_changes = [password]
  }
}

resource "scaleway_rdb_privilege" "noa" {
  instance_id   = scaleway_rdb_instance.main.id
  database_name = scaleway_rdb_database.noa.name
  user_name     = scaleway_rdb_user.noa.name
  permission    = "all"
  region        = var.region
}

# Restrict DB access to the private network only.
resource "scaleway_rdb_acl" "main" {
  instance_id = scaleway_rdb_instance.main.id
  region      = var.region

  dynamic "acl_rules" {
    for_each = var.enable_lb ? [scaleway_lb_ip.main[0].ip_address] : []
    content {
      ip          = "${acl_rules.value}/32"
      description = "Load balancer egress"
    }
  }
  acl_rules {
    ip          = "66.81.172.176/32"
    description = "Developer local machine"
  }
  dynamic "acl_rules" {
    for_each = var.environment == "staging" ? [1] : []
    content {
      ip          = "0.0.0.0/0"
      description = "Serverless containers (no fixed egress IP in staging)"
    }
  }
}
