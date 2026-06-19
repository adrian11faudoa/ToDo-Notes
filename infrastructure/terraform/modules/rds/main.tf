# modules/rds/main.tf
# RDS PostgreSQL 16 with Multi-AZ, encryption, automated backups

resource "aws_db_instance" "main" {
  identifier        = "${var.name}-postgres"
  engine            = "postgres"
  engine_version    = "16.2"
  instance_class    = var.instance_class
  allocated_storage = var.allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true
  kms_key_id        = var.kms_key_arn != "" ? var.kms_key_arn : null

  db_name  = var.database_name
  username = var.database_user
  password = var.database_password

  db_subnet_group_name   = var.db_subnet_group_name
  vpc_security_group_ids = [var.rds_sg_id]

  multi_az               = var.multi_az
  publicly_accessible    = false
  deletion_protection    = var.deletion_protection
  skip_final_snapshot    = !var.deletion_protection
  final_snapshot_identifier = var.deletion_protection ? "${var.name}-final-snapshot" : null

  backup_retention_period = var.backup_retention_days
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  performance_insights_enabled          = true
  performance_insights_retention_period = 7
  monitoring_interval                   = 60
  monitoring_role_arn                   = aws_iam_role.rds_monitoring.arn

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  parameter_group_name = aws_db_parameter_group.main.name

  auto_minor_version_upgrade = true

  tags = var.tags
}

resource "aws_db_parameter_group" "main" {
  name   = "${var.name}-pg16-params"
  family = "postgres16"

  parameter {
    name  = "log_connections"
    value = "1"
  }
  parameter {
    name  = "log_disconnections"
    value = "1"
  }
  parameter {
    name  = "log_duration"
    value = "1"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"   # log queries > 1 second
  }
  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }
  parameter {
    name  = "pg_stat_statements.track"
    value = "all"
  }

  tags = var.tags
}

resource "aws_iam_role" "rds_monitoring" {
  name = "${var.name}-rds-monitoring"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "monitoring.rds.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# ── ElastiCache Redis ─────────────────────────────────────────────

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.name}-redis-subnet"
  subnet_ids = var.private_subnet_ids
  tags       = var.tags
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.name}-redis"
  description          = "NoteFlow Redis cache"

  node_type            = var.redis_node_type
  num_cache_clusters   = var.redis_num_replicas + 1   # 1 primary + replicas
  port                 = 6379

  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [var.redis_sg_id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = var.redis_auth_token

  automatic_failover_enabled = var.redis_num_replicas > 0
  multi_az_enabled           = var.redis_num_replicas > 0

  snapshot_retention_limit = 1
  snapshot_window          = "05:00-06:00"

  tags = var.tags
}
