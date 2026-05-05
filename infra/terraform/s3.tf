# Project data bucket (we already created this manually; importing it would be next step)
resource "aws_s3_bucket" "project" {
  bucket = "${var.project_name}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "project" {
  bucket = aws_s3_bucket.project.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "project" {
  bucket                  = aws_s3_bucket.project.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_caller_identity" "current" {}

output "bucket_name" {
  value = aws_s3_bucket.project.bucket
}