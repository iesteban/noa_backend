terraform {
  required_version = ">= 1.7"

  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.43"
    }
    dns = {
      source  = "hashicorp/dns"
      version = "~> 3.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Terraform state stored in Scaleway Object Storage (S3-compatible).
  # Bootstrap: create the bucket manually once, then run terraform init.
  backend "s3" {
    bucket = "noa-tf-state"
    key    = "noa/terraform.tfstate"
    region = "fr-par"
    endpoints = {
      s3 = "https://s3.fr-par.scw.cloud"
    }
    skip_credentials_validation  = true
    skip_region_validation       = true
    skip_requesting_account_id   = true
    skip_metadata_api_check      = true
    skip_s3_checksum             = true
  }
}

provider "scaleway" {
  zone   = var.zone
  region = var.region
}

provider "dns" {}
provider "random" {}
