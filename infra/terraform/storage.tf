# Application bucket — invoices, budgets, voice notes, photos.
resource "scaleway_object_bucket" "app" {
  name   = "noa-${var.environment}"
  region = var.region

  versioning {
    enabled = false
  }

  lifecycle_rule {
    id      = "expire-voice-notes"
    enabled = true
    prefix  = "voice/"

    expiration {
      days = 90
    }
  }
}

# IAM application + key scoped to this bucket — used by the API container.
resource "scaleway_iam_application" "api" {
  name = "noa-api-${var.environment}"
}

resource "scaleway_iam_policy" "bucket_readwrite" {
  name           = "noa-bucket-readwrite-${var.environment}"
  application_id = scaleway_iam_application.api.id

  rule {
    project_ids          = [scaleway_object_bucket.app.project_id]
    permission_set_names = ["ObjectStorageObjectsRead", "ObjectStorageObjectsWrite", "ObjectStorageObjectsDelete"]
  }
}

resource "scaleway_iam_api_key" "api" {
  application_id = scaleway_iam_application.api.id
  description    = "noa-api bucket access (${var.environment})"
  expires_at     = "2027-05-01T00:00:00Z"
}

# Landing page bucket — public static website, not environment-scoped.
# Only apply this with the production tfvars.
resource "scaleway_object_bucket" "www" {
  name   = "noa-www"
  region = var.region

  website {
    index_document = "index.html"
    error_document = "404.html"
  }
}

resource "scaleway_object_bucket_acl" "www" {
  bucket = scaleway_object_bucket.www.name
  acl    = "public-read"
}
