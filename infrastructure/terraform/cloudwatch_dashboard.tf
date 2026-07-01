# CloudWatch dashboard for LiveCap demo/MVP operational observability.

locals {
  cloudwatch_dashboard_name = var.cloudwatch_dashboard_name != "" ? var.cloudwatch_dashboard_name : "${var.project_name}-${var.environment}-operations"

  alb_full_name         = aws_lb.target.arn_suffix
  alb_target_group_name = aws_lb_target_group.target_backend.arn_suffix

  wake_lambda_function_name = var.enable_wake_endpoint ? aws_lambda_function.wake_backend[0].function_name : "${var.project_name}-wake-backend-${var.environment}"
  cloudfront_waf_name       = "${var.project_name}-cloudfront-waf-${var.environment}"
  alb_waf_name              = "${var.project_name}-alb-waf-${var.environment}"
}

resource "aws_cloudwatch_dashboard" "livecap_operations" {
  count          = var.enable_cloudwatch_dashboard ? 1 : 0
  dashboard_name = local.cloudwatch_dashboard_name

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 3
        properties = {
          markdown = <<-MD
            # LiveCap ${var.environment} Operations

            This dashboard supports Operational Excellence, Reliability, Performance Efficiency, and Cost Optimization for the LiveCap demo/MVP. It tracks ECS backend capacity and utilization, ALB traffic and target health, and optional wake Lambda activity. ECS can scale to zero; ALB fixed hourly cost remains while the environment exists.
          MD
        }
      },
      {
        type   = "text"
        x      = 0
        y      = 3
        width  = 12
        height = 6
        properties = {
          markdown = <<-MD
            ## ECS Task Count Metrics

            ECS CPU and memory utilization are included using standard `AWS/ECS` metrics.

            `RunningTaskCount` and `DesiredTaskCount` require ECS Container Insights (`ECS/ContainerInsights`). Container Insights is intentionally not enabled by default for this cost-sensitive MVP, so task-count widgets are omitted in this batch.
          MD
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 3
        width  = 12
        height = 6
        properties = {
          title   = "ECS CPU and Memory Utilization"
          region  = var.aws_region
          view    = "timeSeries"
          stacked = false
          stat    = "Average"
          period  = 60
          yAxis = {
            left = {
              min = 0
              max = 100
            }
          }
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.target_backend.name],
            [".", "MemoryUtilization", ".", ".", ".", "."]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 9
        width  = 12
        height = 6
        properties = {
          title   = "ALB Requests and Target Status Codes"
          region  = var.aws_region
          view    = "timeSeries"
          stacked = false
          stat    = "Sum"
          period  = 60
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", local.alb_full_name],
            [".", "HTTPCode_Target_2XX_Count", ".", "."],
            [".", "HTTPCode_Target_4XX_Count", ".", "."],
            [".", "HTTPCode_Target_5XX_Count", ".", "."]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 9
        width  = 12
        height = 6
        properties = {
          title   = "ALB Target Response Time"
          region  = var.aws_region
          view    = "timeSeries"
          stacked = false
          stat    = "Average"
          period  = 60
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", local.alb_full_name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 15
        width  = 12
        height = 6
        properties = {
          title   = "ALB Target Health"
          region  = var.aws_region
          view    = "timeSeries"
          stacked = false
          stat    = "Average"
          period  = 60
          metrics = [
            ["AWS/ApplicationELB", "HealthyHostCount", "TargetGroup", local.alb_target_group_name, "LoadBalancer", local.alb_full_name],
            [".", "UnHealthyHostCount", ".", ".", ".", "."]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 15
        width  = 12
        height = 6
        properties = {
          title   = "Wake Lambda Invocations and Errors"
          region  = var.aws_region
          view    = "timeSeries"
          stacked = false
          stat    = "Sum"
          period  = 60
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", local.wake_lambda_function_name],
            [".", "Errors", ".", "."]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 21
        width  = 12
        height = 6
        properties = {
          title   = "Wake Lambda Duration"
          region  = var.aws_region
          view    = "timeSeries"
          stacked = false
          stat    = "Average"
          period  = 60
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", local.wake_lambda_function_name]
          ]
        }
      },
      {
        type   = "text"
        x      = 12
        y      = 21
        width  = 12
        height = 6
        properties = {
          markdown = <<-MD
            ## Operational Notes

            - Running task count near 0 is expected outside active demo/use windows.
            - ALB metrics continue while the environment exists; ALB is not paused by ECS scale-to-zero.
            - Wake Lambda metrics are populated only when `enable_wake_endpoint=true`.
            - Transcribe and Translate are usage-based and mainly cost during active capture sessions.
          MD
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 27
        width  = 12
        height = 6
        properties = {
          title   = "CloudFront WAF COUNT Activity"
          region  = "us-east-1"
          view    = "timeSeries"
          stacked = false
          stat    = "Sum"
          period  = 300
          metrics = [
            ["AWS/WAFV2", "CountedRequests", "WebACL", local.cloudfront_waf_name, "Region", "Global", "Rule", "ALL"],
            [".", "AllowedRequests", ".", ".", ".", ".", ".", "."]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 27
        width  = 12
        height = 6
        properties = {
          title   = "ALB WAF COUNT Activity"
          region  = var.aws_region
          view    = "timeSeries"
          stacked = false
          stat    = "Sum"
          period  = 300
          metrics = [
            ["AWS/WAFV2", "CountedRequests", "WebACL", local.alb_waf_name, "Region", var.aws_region, "Rule", "ALL"],
            [".", "AllowedRequests", ".", ".", ".", ".", ".", "."]
          ]
        }
      }
    ]
  })
}
