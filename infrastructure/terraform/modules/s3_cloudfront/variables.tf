variable "name"                      { type = string }
variable "aws_account_id"            { type = string }
variable "attachments_bucket_name"   { type = string }
variable "exports_bucket_name"       { type = string }
variable "allowed_origins"           { type = list(string) }
variable "cloudfront_price_class"    { type = string; default = "PriceClass_100" }
variable "cloudfront_acm_arn"        { type = string; default = "" }
variable "create_alb_logs_bucket"    { type = bool;   default = true }
variable "tags"                      { type = map(string); default = {} }

output "attachments_bucket_name"     { value = aws_s3_bucket.attachments.bucket }
output "attachments_bucket_arn"      { value = aws_s3_bucket.attachments.arn }
output "exports_bucket_name"         { value = aws_s3_bucket.exports.bucket }
output "cloudfront_domain"           { value = aws_cloudfront_distribution.attachments.domain_name }
output "cloudfront_distribution_id"  { value = aws_cloudfront_distribution.attachments.id }
output "alb_logs_bucket"             { value = var.create_alb_logs_bucket ? aws_s3_bucket.alb_logs[0].bucket : "" }
