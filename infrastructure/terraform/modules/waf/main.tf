# modules/waf/main.tf
# AWS WAF v2 — attached to the ALB
# Protects against: SQLi, XSS, common exploits, rate limiting, bad bots

resource "aws_wafv2_web_acl" "main" {
  name        = "${var.name}-waf"
  description = "NoteFlow WAF — protects ALB"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  # ── Rule 1: AWS Managed — Common Rule Set ─────────────────────
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 10

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"

        # Allow large request bodies for note content
        rule_action_override {
          name = "SizeRestrictions_BODY"
          action_to_use { allow {} }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-common-rules"
      sampled_requests_enabled   = true
    }
  }

  # ── Rule 2: AWS Managed — Known Bad Inputs ────────────────────
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 20

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  # ── Rule 3: AWS Managed — SQL Injection ──────────────────────
  rule {
    name     = "AWSManagedRulesSQLiRuleSet"
    priority = 30

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-sqli"
      sampled_requests_enabled   = true
    }
  }

  # ── Rule 4: AWS Managed — Amazon IP Reputation ───────────────
  rule {
    name     = "AWSManagedRulesAmazonIpReputationList"
    priority = 5

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAmazonIpReputationList"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-ip-reputation"
      sampled_requests_enabled   = true
    }
  }

  # ── Rule 5: Rate limiting — per IP ───────────────────────────
  rule {
    name     = "RateLimitPerIP"
    priority = 40

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.rate_limit_requests_per_5min
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  # ── Rule 6: Rate limiting — auth endpoints (stricter) ────────
  rule {
    name     = "RateLimitAuthEndpoints"
    priority = 41

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.auth_rate_limit_per_5min
        aggregate_key_type = "IP"

        scope_down_statement {
          byte_match_statement {
            search_string         = "/api/v1/auth/"
            positional_constraint = "STARTS_WITH"
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "LOWERCASE"
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-auth-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  # ── Rule 7: Block requests with oversized body (> 10MB) ──────
  rule {
    name     = "BlockOversizedBody"
    priority = 50

    action {
      block {}
    }

    statement {
      size_constraint_statement {
        comparison_operator = "GT"
        size                = 10485760  # 10 MB
        field_to_match {
          body {
            oversize_handling = "MATCH"
          }
        }
        text_transformation {
          priority = 0
          type     = "NONE"
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-oversized-body"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name}-waf"
    sampled_requests_enabled   = true
  }

  tags = var.tags
}

# ── Associate WAF with ALB ────────────────────────────────────────

resource "aws_wafv2_web_acl_association" "alb" {
  resource_arn = var.alb_arn
  web_acl_arn  = aws_wafv2_web_acl.main.arn
}

# ── WAF Logging ───────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "waf" {
  # WAF log groups MUST be prefixed with aws-waf-logs-
  name              = "aws-waf-logs-${var.name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_wafv2_web_acl_logging_configuration" "main" {
  log_destination_configs = [aws_cloudwatch_log_group.waf.arn]
  resource_arn            = aws_wafv2_web_acl.main.arn

  logging_filter {
    default_behavior = "DROP"

    filter {
      behavior    = "KEEP"
      requirement = "MEETS_ANY"

      condition {
        action_condition {
          action = "BLOCK"
        }
      }
    }
  }
}

variable "name"                         { type = string }
variable "alb_arn"                      { type = string }
variable "rate_limit_requests_per_5min" { type = number; default = 2000 }
variable "auth_rate_limit_per_5min"     { type = number; default = 100 }
variable "log_retention_days"           { type = number; default = 30 }
variable "tags"                         { type = map(string); default = {} }

output "web_acl_arn"  { value = aws_wafv2_web_acl.main.arn }
output "web_acl_id"   { value = aws_wafv2_web_acl.main.id }
