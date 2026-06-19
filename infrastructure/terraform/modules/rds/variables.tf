variable "name"                 { type = string }
variable "db_subnet_group_name"  { type = string }
variable "rds_sg_id"             { type = string }
variable "redis_sg_id"           { type = string }
variable "private_subnet_ids"    { type = list(string) }
variable "database_name"         { type = string; default = "noteflow" }
variable "database_user"         { type = string; default = "noteflow" }
variable "database_password"     { type = string; sensitive = true }
variable "instance_class"        { type = string; default = "db.t4g.small" }
variable "allocated_storage"     { type = number; default = 20 }
variable "multi_az"              { type = bool;   default = false }
variable "deletion_protection"   { type = bool;   default = false }
variable "backup_retention_days" { type = number; default = 7 }
variable "kms_key_arn"           { type = string; default = "" }
variable "redis_node_type"       { type = string; default = "cache.t4g.small" }
variable "redis_num_replicas"    { type = number; default = 0 }
variable "redis_auth_token"      { type = string; sensitive = true }
variable "tags"                  { type = map(string); default = {} }

output "db_endpoint"            { value = aws_db_instance.main.endpoint }
output "db_port"                { value = aws_db_instance.main.port }
output "db_name"                { value = aws_db_instance.main.db_name }
output "redis_endpoint"         { value = aws_elasticache_replication_group.main.primary_endpoint_address }
output "redis_port"             { value = aws_elasticache_replication_group.main.port }
