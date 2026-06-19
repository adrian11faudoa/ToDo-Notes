# modules/ecs/main.tf
# ECS Fargate cluster + ALB + auto-scaling + ECR repository

# ── ECR Repository ────────────────────────────────────────────────

resource "aws_ecr_repository" "api" {
  name                 = "${var.name}/api"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

# ── CloudWatch Log Group ──────────────────────────────────────────

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.name}/api"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# ── IAM Roles ─────────────────────────────────────────────────────

# Task execution role — ECS agent pulls image, writes logs
resource "aws_iam_role" "execution" {
  name = "${var.name}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow execution role to read Secrets Manager
resource "aws_iam_role_policy" "execution_secrets" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "ssm:GetParameters", "kms:Decrypt"]
      Resource = ["*"]
    }]
  })
}

# Task role — what the running container can do
resource "aws_iam_role" "task" {
  name = "${var.name}-ecs-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "task_s3" {
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3Attachments"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject",
                  "s3:DeleteObjects", "s3:HeadObject"]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket_attachments}/*",
          "arn:aws:s3:::${var.s3_bucket_exports}/*",
        ]
      },
      {
        Sid    = "S3ListBuckets"
        Effect = "Allow"
        Action = ["s3:HeadBucket", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket_attachments}",
          "arn:aws:s3:::${var.s3_bucket_exports}",
        ]
      },
      {
        Sid      = "CloudWatchMetrics"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = ["*"]
      },
      {
        Sid    = "SecretsManager"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = [var.secrets_arn]
      },
      {
        Sid    = "SES"
        Effect = "Allow"
        Action = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = ["*"]
      }
    ]
  })
}

# ── ECS Cluster ───────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${var.name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = var.tags
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# ── Task Definition ───────────────────────────────────────────────

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
      essential = true

      portMappings = [{
        containerPort = 8000
        protocol      = "tcp"
      }]

      environment = [
        { name = "ENVIRONMENT",              value = var.environment },
        { name = "LOG_LEVEL",               value = var.log_level },
        { name = "DATABASE_HOST",           value = var.db_host },
        { name = "DATABASE_PORT",           value = tostring(var.db_port) },
        { name = "DATABASE_NAME",           value = var.db_name },
        { name = "DATABASE_USER",           value = var.db_user },
        { name = "REDIS_HOST",              value = var.redis_host },
        { name = "REDIS_PORT",              value = tostring(var.redis_port) },
        { name = "REDIS_SSL",               value = "true" },
        { name = "AWS_REGION",              value = var.aws_region },
        { name = "S3_BUCKET_ATTACHMENTS",   value = var.s3_bucket_attachments },
        { name = "S3_BUCKET_EXPORTS",       value = var.s3_bucket_exports },
        { name = "SECRETS_MANAGER_ARN",     value = var.secrets_arn },
        { name = "GUNICORN_WORKERS",        value = tostring(var.gunicorn_workers) },
        { name = "ALLOWED_ORIGINS",         value = join(",", var.allowed_origins) },
        { name = "SENTRY_DSN",              value = var.sentry_dsn },
        { name = "CLOUDWATCH_LOG_GROUP",    value = "/ecs/${var.name}/api" },
      ]

      secrets = [
        {
          name      = "DATABASE_PASSWORD"
          valueFrom = "${var.secrets_arn}:DATABASE_PASSWORD::"
        },
        {
          name      = "SECRET_KEY"
          valueFrom = "${var.secrets_arn}:SECRET_KEY::"
        },
        {
          name      = "REDIS_PASSWORD"
          valueFrom = "${var.secrets_arn}:REDIS_PASSWORD::"
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/ready || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }

      readonlyRootFilesystem = false
      user                   = "1001:1001"
    }
  ])

  tags = var.tags
}

# ── Application Load Balancer ─────────────────────────────────────

resource "aws_lb" "main" {
  name               = "${var.name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_sg_id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection       = var.environment == "production"
  enable_cross_zone_load_balancing = true
  drop_invalid_header_fields       = true

  access_logs {
    bucket  = var.alb_logs_bucket
    prefix  = "alb"
    enabled = var.alb_logs_bucket != ""
  }

  tags = var.tags
}

resource "aws_lb_target_group" "api" {
  name        = "${var.name}-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = var.tags
}

# HTTP → HTTPS redirect
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# ── ECS Service ───────────────────────────────────────────────────

resource "aws_ecs_service" "api" {
  name                               = "${var.name}-api"
  cluster                            = aws_ecs_cluster.main.id
  task_definition                    = aws_ecs_task_definition.api.arn
  desired_count                      = var.desired_count
  launch_type                        = "FARGATE"
  platform_version                   = "LATEST"
  health_check_grace_period_seconds  = 60
  enable_execute_command             = var.environment != "production"
  force_new_deployment               = true

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_sg_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_controller {
    type = "ECS"
  }

  lifecycle {
    ignore_changes = [desired_count]   # managed by autoscaling
  }

  tags = var.tags
}

# ── Auto Scaling ──────────────────────────────────────────────────

resource "aws_appautoscaling_target" "api" {
  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.name}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

resource "aws_appautoscaling_policy" "memory" {
  name               = "${var.name}-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value       = 80.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

resource "aws_appautoscaling_policy" "request_count" {
  name               = "${var.name}-request-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.main.arn_suffix}/${aws_lb_target_group.api.arn_suffix}"
    }
    target_value       = 1000
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
