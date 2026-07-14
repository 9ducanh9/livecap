# Optional wake-on-demand endpoint for scale-to-zero demo environments.
# The Function URL requires AWS_IAM and is reachable by the browser only through
# the signed CloudFront /api/wake behavior.

locals {
  wake_endpoint_allowed_origins = var.custom_domain != "" ? ["https://${var.custom_domain}"] : ["*"]

  wake_endpoint_allowed_origin = join(",", local.wake_endpoint_allowed_origins)
  # The migration wake endpoint always controls the private target service.
  # CloudFront routing remains an independent blue/green cutover gate.
  wake_backend_service_name = "${var.project_name}-target-service-${var.environment}"
  wake_backend_service_arn  = "arn:${data.aws_partition.current.partition}:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${aws_ecs_cluster.main.name}/${local.wake_backend_service_name}"
}

data "aws_partition" "current" {}

resource "aws_cloudfront_origin_access_control" "wake_backend" {
  count = var.enable_wake_endpoint ? 1 : 0

  name                              = "${var.project_name}-wake-${var.environment}-oac"
  description                       = "SigV4 access from CloudFront to the LiveCap wake Lambda Function URL"
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "archive_file" "wake_backend" {
  count       = var.enable_wake_endpoint ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/.terraform/wake-backend.zip"

  source {
    filename = "lambda_function.py"
    content  = <<-PY
      import json
      import os

      import boto3

      ecs = boto3.client("ecs")

      CLUSTER_NAME = os.environ["CLUSTER_NAME"]
      SERVICE_NAME = os.environ["SERVICE_NAME"]
      def _headers():
          return {
              "Cache-Control": "no-store",
              "Content-Type": "application/json",
          }


      def handler(event, context):
          method = event.get("requestContext", {}).get("http", {}).get("method", "POST")

          if method == "OPTIONS":
              return {"statusCode": 204, "headers": _headers(), "body": ""}

          if method != "POST":
              return {
                  "statusCode": 405,
                  "headers": _headers(),
                  "body": json.dumps({
                      "status": "error",
                      "error": "METHOD_NOT_ALLOWED",
                      "cluster": CLUSTER_NAME,
                      "service": SERVICE_NAME,
                  }),
              }

          service = ecs.describe_services(cluster=CLUSTER_NAME, services=[SERVICE_NAME])["services"][0]
          desired_count = service.get("desiredCount", 0)
          running_count = service.get("runningCount", 0)
          if running_count > 0 and desired_count > 0:
              return {
                  "statusCode": 200,
                  "headers": _headers(),
                  "body": json.dumps({
                      "status": "already_running",
                      "cluster": CLUSTER_NAME,
                      "service": SERVICE_NAME,
                  }),
              }

          if desired_count < 1:
              ecs.update_service(
                  cluster=CLUSTER_NAME,
                  service=SERVICE_NAME,
                  desiredCount=1,
              )

          return {
              "statusCode": 202,
              "headers": _headers(),
              "body": json.dumps({
                  "status": "waking",
                  "cluster": CLUSTER_NAME,
                  "service": SERVICE_NAME,
              }),
          }
    PY
  }
}

resource "aws_iam_role" "wake_backend" {
  count = var.enable_wake_endpoint ? 1 : 0
  name  = "${var.project_name}-wake-backend-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "wake_backend" {
  count = var.enable_wake_endpoint ? 1 : 0
  name  = "${var.project_name}-wake-backend-${var.environment}"
  role  = aws_iam_role.wake_backend[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeServices",
          "ecs:UpdateService"
        ]
        Resource = local.wake_backend_service_arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "wake_backend_basic_execution" {
  count      = var.enable_wake_endpoint ? 1 : 0
  role       = aws_iam_role.wake_backend[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "wake_backend" {
  count = var.enable_wake_endpoint ? 1 : 0

  function_name    = "${var.project_name}-wake-backend-${var.environment}"
  role             = aws_iam_role.wake_backend[0].arn
  handler          = "lambda_function.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.wake_backend[0].output_path
  source_code_hash = data.archive_file.wake_backend[0].output_base64sha256
  timeout          = var.wake_endpoint_timeout_seconds

  environment {
    variables = {
      CLUSTER_NAME   = aws_ecs_cluster.main.name
      SERVICE_NAME   = local.wake_backend_service_name
      ALLOWED_ORIGIN = local.wake_endpoint_allowed_origin
    }
  }

  depends_on = [
    aws_iam_role_policy.wake_backend,
    aws_iam_role_policy_attachment.wake_backend_basic_execution,
  ]
}

resource "aws_lambda_function_url" "wake_backend" {
  count              = var.enable_wake_endpoint ? 1 : 0
  function_name      = aws_lambda_function.wake_backend[0].function_name
  authorization_type = "AWS_IAM"

  cors {
    allow_credentials = false
    allow_headers     = ["content-type", "x-amz-content-sha256"]
    allow_methods     = ["POST"]
    allow_origins     = local.wake_endpoint_allowed_origins
    max_age           = 300
  }
}

resource "aws_lambda_permission" "wake_backend_function_url" {
  count = var.enable_wake_endpoint ? 1 : 0

  statement_id  = "AllowCloudFrontFunctionUrlInvoke"
  action        = "lambda:InvokeFunctionUrl"
  function_name = aws_lambda_function.wake_backend[0].function_name
  principal     = "cloudfront.amazonaws.com"
  source_arn    = aws_cloudfront_distribution.frontend.arn
}

resource "aws_lambda_permission" "wake_backend_function" {
  count = var.enable_wake_endpoint ? 1 : 0

  statement_id  = "AllowCloudFrontFunctionInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.wake_backend[0].function_name
  principal     = "cloudfront.amazonaws.com"
  source_arn    = aws_cloudfront_distribution.frontend.arn
}
