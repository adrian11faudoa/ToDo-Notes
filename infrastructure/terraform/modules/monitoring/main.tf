# modules/monitoring/main.tf
# CloudWatch alarms, dashboard, SNS alert topic

# ── SNS Alert Topic ───────────────────────────────────────────────

resource "aws_sns_topic" "alerts" {
  name = "${var.name}-alerts"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ── CloudWatch Alarms ─────────────────────────────────────────────

# API 5xx error rate
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.name}-api-5xx"
  alarm_description   = "API 5xx error rate > 5%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 5
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "error_rate"
    expression  = "(errors/requests)*100"
    label       = "5xx Error Rate %"
    return_data = true
  }
  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_Target_5XX_Count"
      dimensions  = { LoadBalancer = var.alb_arn_suffix }
      period      = 60
      stat        = "Sum"
    }
  }
  metric_query {
    id = "requests"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "RequestCount"
      dimensions  = { LoadBalancer = var.alb_arn_suffix }
      period      = 60
      stat        = "Sum"
    }
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# API latency P99
resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "${var.name}-api-p99-latency"
  alarm_description   = "API P99 latency > 2s"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 2000
  treat_missing_data  = "notBreaching"

  namespace   = "AWS/ApplicationELB"
  metric_name = "TargetResponseTime"
  dimensions  = { LoadBalancer = var.alb_arn_suffix }
  period      = 60
  statistic   = "p99"
  unit        = "Milliseconds"

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# ECS CPU
resource "aws_cloudwatch_metric_alarm" "ecs_cpu" {
  alarm_name          = "${var.name}-ecs-cpu"
  alarm_description   = "ECS CPU utilization > 85%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 85
  treat_missing_data  = "notBreaching"

  namespace   = "AWS/ECS"
  metric_name = "CPUUtilization"
  dimensions  = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }
  period    = 60
  statistic = "Average"

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# ECS Memory
resource "aws_cloudwatch_metric_alarm" "ecs_memory" {
  alarm_name          = "${var.name}-ecs-memory"
  alarm_description   = "ECS memory utilization > 85%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 85
  treat_missing_data  = "notBreaching"

  namespace   = "AWS/ECS"
  metric_name = "MemoryUtilization"
  dimensions  = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }
  period    = 60
  statistic = "Average"

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# RDS CPU
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.name}-rds-cpu"
  alarm_description   = "RDS CPU > 80%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 80
  treat_missing_data  = "notBreaching"

  namespace   = "AWS/RDS"
  metric_name = "CPUUtilization"
  dimensions  = { DBInstanceIdentifier = var.db_instance_id }
  period      = 60
  statistic   = "Average"

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# RDS Storage
resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "${var.name}-rds-storage"
  alarm_description   = "RDS free storage < 5GB"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  threshold           = 5368709120   # 5 GB in bytes
  treat_missing_data  = "notBreaching"

  namespace   = "AWS/RDS"
  metric_name = "FreeStorageSpace"
  dimensions  = { DBInstanceIdentifier = var.db_instance_id }
  period      = 300
  statistic   = "Minimum"

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# RDS Connections
resource "aws_cloudwatch_metric_alarm" "rds_connections" {
  alarm_name          = "${var.name}-rds-connections"
  alarm_description   = "RDS connections > 80% of max"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 80
  treat_missing_data  = "notBreaching"

  namespace   = "AWS/RDS"
  metric_name = "DatabaseConnections"
  dimensions  = { DBInstanceIdentifier = var.db_instance_id }
  period      = 60
  statistic   = "Average"

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# ── CloudWatch Dashboard ──────────────────────────────────────────

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.name}-overview"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0; y = 0; width = 12; height = 6
        properties = {
          title   = "API Request Rate & Errors"
          period  = 60
          metrics = [
            ["AWS/ApplicationELB", "RequestCount",
             "LoadBalancer", var.alb_arn_suffix, { stat = "Sum", label = "Requests" }],
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count",
             "LoadBalancer", var.alb_arn_suffix, { stat = "Sum", label = "5xx Errors", color = "#d13212" }],
            ["AWS/ApplicationELB", "HTTPCode_Target_4XX_Count",
             "LoadBalancer", var.alb_arn_suffix, { stat = "Sum", label = "4xx Errors", color = "#ff9900" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12; y = 0; width = 12; height = 6
        properties = {
          title   = "API Latency (P50 / P99)"
          period  = 60
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime",
             "LoadBalancer", var.alb_arn_suffix, { stat = "p50", label = "P50" }],
            ["AWS/ApplicationELB", "TargetResponseTime",
             "LoadBalancer", var.alb_arn_suffix, { stat = "p99", label = "P99", color = "#d13212" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0; y = 6; width = 12; height = 6
        properties = {
          title   = "ECS CPU & Memory"
          period  = 60
          metrics = [
            ["AWS/ECS", "CPUUtilization",
             "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name,
             { stat = "Average", label = "CPU %" }],
            ["AWS/ECS", "MemoryUtilization",
             "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name,
             { stat = "Average", label = "Memory %", color = "#1f77b4" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12; y = 6; width = 12; height = 6
        properties = {
          title   = "RDS CPU & Connections"
          period  = 60
          metrics = [
            ["AWS/RDS", "CPUUtilization",
             "DBInstanceIdentifier", var.db_instance_id,
             { stat = "Average", label = "CPU %" }],
            ["AWS/RDS", "DatabaseConnections",
             "DBInstanceIdentifier", var.db_instance_id,
             { stat = "Average", label = "Connections", yAxis = "right" }],
          ]
        }
      },
    ]
  })
}

variable "name"             { type = string }
variable "alb_arn_suffix"   { type = string }
variable "ecs_cluster_name" { type = string }
variable "ecs_service_name" { type = string }
variable "db_instance_id"   { type = string }
variable "alert_email"      { type = string; default = "" }
variable "tags"             { type = map(string); default = {} }

output "sns_topic_arn"      { value = aws_sns_topic.alerts.arn }
output "dashboard_url"      { value = "https://console.aws.amazon.com/cloudwatch/home#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}" }
