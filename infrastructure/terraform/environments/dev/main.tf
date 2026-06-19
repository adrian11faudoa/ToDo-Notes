# environments/dev/main.tf
# Dev environment — minimal cost, single-AZ, no deletion protection

terraform {
  required_version = ">= 1.7"
  required_providers {
    aws    = { source = "hashicorp/aws"; version = "~> 5.50" }
    random = { source = "hashicorp/random"; version = "~> 3.6" }
  }
  backend "s3" {
    bucket         = "noteflow-terraform-state-dev"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "noteflow-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region
  default_tags { tags = { Project = "NoteFlow", Environment = "dev", ManagedBy = "Terraform" } }
}

resource "random_password" "db_password"    { length = 24; special = false }
resource "random_password" "secret_key"     { length = 48; special = false }
resource "random_password" "redis_password" { length = 24; special = false }

module "secrets" {
  source            = "../../modules/secrets"
  name              = "noteflow-dev"
  database_password = random_password.db_password.result
  secret_key        = random_password.secret_key.result
  redis_password    = random_password.redis_password.result
  create_kms_key    = false
  recovery_window_days = 0   # immediate delete in dev
}

module "vpc" {
  source             = "../../modules/vpc"
  name               = "noteflow-dev"
  vpc_cidr           = "10.1.0.0/16"
  enable_nat_gateway = true
}

module "storage" {
  source                  = "../../modules/s3_cloudfront"
  name                    = "noteflow-dev"
  aws_account_id          = var.aws_account_id
  attachments_bucket_name = "noteflow-attachments-${var.aws_account_id}-dev"
  exports_bucket_name     = "noteflow-exports-${var.aws_account_id}-dev"
  allowed_origins         = ["http://localhost:3000", "http://localhost:5173"]
  create_alb_logs_bucket  = false
}

module "data" {
  source                = "../../modules/rds"
  name                  = "noteflow-dev"
  db_subnet_group_name  = module.vpc.db_subnet_group_name
  rds_sg_id             = module.vpc.rds_sg_id
  redis_sg_id           = module.vpc.redis_sg_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  database_password     = random_password.db_password.result
  instance_class        = "db.t4g.micro"
  allocated_storage     = 20
  multi_az              = false
  deletion_protection   = false
  backup_retention_days = 1
  redis_node_type       = "cache.t4g.micro"
  redis_num_replicas    = 0
  redis_auth_token      = random_password.redis_password.result
}

module "ecs" {
  source               = "../../modules/ecs"
  name                 = "noteflow-dev"
  environment          = "development"
  aws_region           = var.aws_region
  vpc_id               = module.vpc.vpc_id
  public_subnet_ids    = module.vpc.public_subnet_ids
  private_subnet_ids   = module.vpc.private_subnet_ids
  alb_sg_id            = module.vpc.alb_sg_id
  ecs_sg_id            = module.vpc.ecs_sg_id
  acm_certificate_arn  = var.acm_certificate_arn
  task_cpu             = 256
  task_memory          = 512
  desired_count        = 1
  min_capacity         = 1
  max_capacity         = 3
  gunicorn_workers     = 1
  log_retention_days   = 7
  db_host              = module.data.db_endpoint
  db_port              = module.data.db_port
  db_name              = "noteflow"
  db_user              = "noteflow"
  redis_host           = module.data.redis_endpoint
  redis_port           = module.data.redis_port
  s3_bucket_attachments = module.storage.attachments_bucket_name
  s3_bucket_exports    = module.storage.exports_bucket_name
  secrets_arn          = module.secrets.secrets_arn
  allowed_origins      = ["http://localhost:3000", "http://localhost:5173"]
}

variable "aws_region"          { type = string; default = "us-east-1" }
variable "aws_account_id"      { type = string }
variable "acm_certificate_arn" { type = string; default = "" }

output "api_url"            { value = "http://${module.ecs.alb_dns_name}" }
output "ecr_repository_url" { value = module.ecs.ecr_repository_url }
output "db_endpoint"        { value = module.data.db_endpoint; sensitive = true }
