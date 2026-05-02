# Private network — isolates database from the public internet.
# The container connects via the public DB endpoint (with TLS + password),
# keeping the setup simple while the project is small. The VPC is in place
# so a private endpoint can be added later without Terraform restructuring.
resource "scaleway_vpc_private_network" "main" {
  name   = "noa-${var.environment}"
  region = var.region
}
