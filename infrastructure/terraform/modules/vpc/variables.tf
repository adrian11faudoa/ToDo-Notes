variable "name"              { type = string }
variable "vpc_cidr"          { type = string; default = "10.0.0.0/16" }
variable "enable_nat_gateway" { type = bool;   default = true }
variable "tags"              { type = map(string); default = {} }

output "vpc_id"              { value = aws_vpc.main.id }
output "public_subnet_ids"   { value = aws_subnet.public[*].id }
output "private_subnet_ids"  { value = aws_subnet.private[*].id }
output "database_subnet_ids" { value = aws_subnet.database[*].id }
output "db_subnet_group_name"{ value = aws_db_subnet_group.main.name }
output "alb_sg_id"           { value = aws_security_group.alb.id }
output "ecs_sg_id"           { value = aws_security_group.ecs.id }
output "rds_sg_id"           { value = aws_security_group.rds.id }
output "redis_sg_id"         { value = aws_security_group.redis.id }
