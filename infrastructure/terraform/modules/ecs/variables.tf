variable "name"                { type = string }
variable "environment"          { type = string }
variable "aws_region"           { type = string }
variable "vpc_id"               { type = string }
variable "public_subnet_ids"    { type = list(string) }
variable "private_subnet_ids"   { type = list(string) }
variable "alb_sg_id"            { type = string }
variable "ecs_sg_id"            { type = string }
variable "acm_certificate_arn"  { type = string }
variable "image_tag"            { type = string; default = "latest" }
variable "task_cpu"             { type = number; default = 512 }
variable "task_memory"          { type = number; default = 1024 }
variable "desired_count"        { type = number; default = 2 }
variable "min_capacity"         { type = number; default = 1 }
variable "max_capacity"         { type = number; default = 10 }
variable "gunicorn_workers"     { type = number; default = 2 }
variable "log_retention_days"   { type = number; default = 30 }
variable "log_level"            { type = string; default = "info" }
variable "db_host"              { type = string }
variable "db_port"              { type = number; default = 5432 }
variable "db_name"              { type = string }
variable "db_user"              { type = string }
variable "redis_host"           { type = string }
variable "redis_port"           { type = number; default = 6379 }
variable "s3_bucket_attachments" { type = string }
variable "s3_bucket_exports"    { type = string }
variable "secrets_arn"          { type = string }
variable "allowed_origins"      { type = list(string) }
variable "sentry_dsn"           { type = string; default = "" }
variable "alb_logs_bucket"      { type = string; default = "" }
variable "tags"                 { type = map(string); default = {} }

output "ecr_repository_url"    { value = aws_ecr_repository.api.repository_url }
output "alb_dns_name"          { value = aws_lb.main.dns_name }
output "alb_zone_id"           { value = aws_lb.main.zone_id }
output "alb_arn"               { value = aws_lb.main.arn }
output "alb_arn_suffix"        { value = aws_lb.main.arn_suffix }
output "target_group_arn_suffix" { value = aws_lb_target_group.api.arn_suffix }
output "cluster_name"          { value = aws_ecs_cluster.main.name }
output "service_name"          { value = aws_ecs_service.api.name }
