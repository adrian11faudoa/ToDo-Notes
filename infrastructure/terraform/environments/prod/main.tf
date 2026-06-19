# environments/prod/main.tf
# Production environment — wires all modules together

terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state in S3 — create this bucket manually before first apply
  backend "s3" {
    bucket         = "noteflow-terraform-state-prod"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "noteflow-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

locals {
  name = "noteflow-${var.environment}"
  common_tags = {
    Project     = "NoteFlow"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# ── Random password generation ────────────────────────────────────

resource "random_password" "db_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

resource "random_password" "redis_password" {
  length  = 32
  special = false
}

# ── Secrets Manager ───────────────────────────────────────────────

module "secrets" {
  source = "../../modules/secrets"
  name              = local.name
  database_password = random_password.db_password.result
  secret_key        = random_password.secret_key.result
  redis_password    = random_password.redis_password.result
  create_kms_key    = true
  tags              = local.common_tags
}

# ── VPC ──────────────────────────────────────────────────────────

module "vpc" {
  source             = "../../modules/vpc"
  name               = local.name
  vpc_cidr           = var.vpc_cidr
  enable_nat_gateway = true
  tags               = local.common_tags
}

# ── S3 + CloudFront ───────────────────────────────────────────────

module "storage" {
  source                  = "../../modules/s3_cloudfront"
  name                    = local.name
  aws_account_id          = var.aws_account_id
  attachments_bucket_name = "noteflow-attachments-${var.aws_account_id}-prod"
  exports_bucket_name     = "noteflow-exports-${var.aws_account_id}-prod"
  allowed_origins         = var.allowed_origins
  cloudfront_price_class  = "PriceClass_100"
  cloudfront_acm_arn      = var.cloudfront_acm_arn
  create_alb_logs_bucket  = true
  tags                    = local.common_tags
}

# ── RDS + ElastiCache ─────────────────────────────────────────────

module "data" {
  source                = "../../modules/rds"
  name                  = local.name
  db_subnet_group_name  = module.vpc.db_subnet_group_name
  rds_sg_id             = module.vpc.rds_sg_id
  redis_sg_id           = module.vpc.redis_sg_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  database_name         = "noteflow"
  database_user         = "noteflow"
  database_password     = random_password.db_password.result
  instance_class        = var.rds_instance_class
  allocated_storage     = var.rds_storage_gb
  multi_az              = true
  deletion_protection   = true
  backup_retention_days = 14
  kms_key_arn           = module.secrets.kms_key_arn
  redis_node_type       = var.redis_node_type
  redis_num_replicas    = 1
  redis_auth_token      = random_password.redis_password.result
  tags                  = local.common_tags
}

# ── ECS Fargate ───────────────────────────────────────────────────

module "ecs" {
  source               = "../../modules/ecs"
  name                 = local.name
  environment          = var.environment
  aws_region           = var.aws_region
  vpc_id               = module.vpc.vpc_id
  public_subnet_ids    = module.vpc.public_subnet_ids
  private_subnet_ids   = module.vpc.private_subnet_ids
  alb_sg_id            = module.vpc.alb_sg_id
  ecs_sg_id            = module.vpc.ecs_sg_id
  acm_certificate_arn  = var.acm_certificate_arn
  image_tag            = var.image_tag
  task_cpu             = 1024
  task_memory          = 2048
  desired_count        = 2
  min_capacity         = 2
  max_capacity         = 20
  gunicorn_workers     = 4
  log_retention_days   = 90
  db_host              = module.data.db_endpoint
  db_port              = module.data.db_port
  db_name              = "noteflow"
  db_user              = "noteflow"
  redis_host           = module.data.redis_endpoint
  redis_port           = module.data.redis_port
  s3_bucket_attachments = module.storage.attachments_bucket_name
  s3_bucket_exports    = module.storage.exports_bucket_name
  secrets_arn          = module.secrets.secrets_arn
  allowed_origins      = var.allowed_origins
  sentry_dsn           = var.sentry_dsn
  alb_logs_bucket      = module.storage.alb_logs_bucket
  tags                 = local.common_tags
}

# ── Route53 DNS ───────────────────────────────────────────────────

data "aws_route53_zone" "main" {
  count        = var.route53_zone_id != "" ? 1 : 0
  zone_id      = var.route53_zone_id
  private_zone = false
}

resource "aws_route53_record" "api" {
  count   = var.route53_zone_id != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = module.ecs.alb_dns_name
    zone_id                = module.ecs.alb_zone_id
    evaluate_target_health = true
  }
}

# ── WAF ───────────────────────────────────────────────────────────

module "waf" {
  source                       = "../../modules/waf"
  name                          = local.name
  alb_arn                       = module.ecs.alb_arn
  rate_limit_requests_per_5min  = 2000
  auth_rate_limit_per_5min      = 100
  log_retention_days            = 90
  tags                          = local.common_tags
}

# ── Monitoring ────────────────────────────────────────────────────

module "monitoring" {
  source           = "../../modules/monitoring"
  name             = local.name
  alb_arn_suffix   = module.ecs.alb_arn_suffix
  ecs_cluster_name = module.ecs.cluster_name
  ecs_service_name = module.ecs.service_name
  db_instance_id   = "${local.name}-postgres"
  alert_email      = var.alert_email
  tags             = local.common_tags
}

# ── Outputs ───────────────────────────────────────────────────────

output "api_url"             { value = "https://api.${var.domain_name}" }
output "alb_dns_name"        { value = module.ecs.alb_dns_name }
output "ecr_repository_url"  { value = module.ecs.ecr_repository_url }
output "cloudfront_domain"   { value = module.storage.cloudfront_domain }
output "db_endpoint"         { value = module.data.db_endpoint; sensitive = true }
output "redis_endpoint"      { value = module.data.redis_endpoint; sensitive = true }
output "secrets_arn"         { value = module.secrets.secrets_arn }
output "dashboard_url"       { value = module.monitoring.dashboard_url }
output "waf_web_acl_arn"     { value = module.waf.web_acl_arn }
