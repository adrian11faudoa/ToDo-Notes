variable "aws_region"           { type = string; default = "us-east-1" }
variable "aws_account_id"       { type = string }
variable "environment"          { type = string; default = "production" }
variable "domain_name"          { type = string; description = "e.g. noteflow.app" }
variable "vpc_cidr"             { type = string; default = "10.0.0.0/16" }
variable "acm_certificate_arn"  { type = string; description = "ACM cert ARN for ALB HTTPS" }
variable "cloudfront_acm_arn"   { type = string; default = ""; description = "ACM cert in us-east-1 for CloudFront" }
variable "route53_zone_id"      { type = string; default = "" }
variable "rds_instance_class"   { type = string; default = "db.t4g.medium" }
variable "rds_storage_gb"       { type = number; default = 50 }
variable "redis_node_type"      { type = string; default = "cache.t4g.small" }
variable "image_tag"            { type = string; default = "latest" }
variable "allowed_origins"      { type = list(string); default = ["https://noteflow.app"] }
variable "sentry_dsn"           { type = string; default = ""; sensitive = true }
variable "alert_email"          { type = string; default = "" }
