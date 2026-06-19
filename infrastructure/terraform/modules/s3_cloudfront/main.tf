# modules/s3_cloudfront/main.tf
# S3 buckets for attachments + exports
# CloudFront distribution for global CDN delivery

# ── S3: Attachments ───────────────────────────────────────────────

resource "aws_s3_bucket" "attachments" {
  bucket = var.attachments_bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "attachments" {
  bucket = aws_s3_bucket.attachments.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "attachments" {
  bucket                  = aws_s3_bucket.attachments.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id
  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "HEAD"]
    allowed_origins = var.allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id
  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    noncurrent_version_expiration { noncurrent_days = 30 }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

# ── S3: Exports ───────────────────────────────────────────────────

resource "aws_s3_bucket" "exports" {
  bucket = var.exports_bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "exports" {
  bucket = aws_s3_bucket.exports.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "exports" {
  bucket                  = aws_s3_bucket.exports.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "exports" {
  bucket = aws_s3_bucket.exports.id
  rule {
    id     = "expire-exports"
    status = "Enabled"
    expiration { days = 7 }   # exports auto-expire after 7 days
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
}

# ── S3: ALB Access Logs ───────────────────────────────────────────

resource "aws_s3_bucket" "alb_logs" {
  count  = var.create_alb_logs_bucket ? 1 : 0
  bucket = "${var.name}-alb-logs-${var.aws_account_id}"
  tags   = var.tags
}

resource "aws_s3_bucket_public_access_block" "alb_logs" {
  count  = var.create_alb_logs_bucket ? 1 : 0
  bucket = aws_s3_bucket.alb_logs[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_elb_service_account" "main" {}

resource "aws_s3_bucket_policy" "alb_logs" {
  count  = var.create_alb_logs_bucket ? 1 : 0
  bucket = aws_s3_bucket.alb_logs[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = data.aws_elb_service_account.main.arn }
      Action    = "s3:PutObject"
      Resource  = "${aws_s3_bucket.alb_logs[0].arn}/alb/*"
    }]
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "alb_logs" {
  count  = var.create_alb_logs_bucket ? 1 : 0
  bucket = aws_s3_bucket.alb_logs[0].id
  rule {
    id     = "expire-logs"
    status = "Enabled"
    expiration { days = 90 }
  }
}

# ── CloudFront: Attachments CDN ───────────────────────────────────

resource "aws_cloudfront_origin_access_control" "attachments" {
  name                              = "${var.name}-attachments-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "attachments" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.name} attachments CDN"
  price_class         = var.cloudfront_price_class
  wait_for_deployment = false

  origin {
    domain_name              = aws_s3_bucket.attachments.bucket_regional_domain_name
    origin_id                = "s3-attachments"
    origin_access_control_id = aws_cloudfront_origin_access_control.attachments.id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-attachments"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 604800

    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.cloudfront_acm_arn == ""
    acm_certificate_arn            = var.cloudfront_acm_arn != "" ? var.cloudfront_acm_arn : null
    ssl_support_method             = var.cloudfront_acm_arn != "" ? "sni-only" : null
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  tags = var.tags
}

# Allow CloudFront OAC to read from S3
resource "aws_s3_bucket_policy" "attachments" {
  bucket = aws_s3_bucket.attachments.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontOAC"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.attachments.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.attachments.arn
        }
      }
    }]
  })
}

# ── Security Headers Policy ───────────────────────────────────────

resource "aws_cloudfront_response_headers_policy" "security" {
  name = "${var.name}-security-headers"

  security_headers_config {
    content_type_options { override = true }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }
    xss_protection {
      mode_block = true
      protection = true
      override   = true
    }
  }
}
