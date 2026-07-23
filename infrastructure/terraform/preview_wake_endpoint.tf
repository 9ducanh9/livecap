# Preview wake endpoint. It is a separate Lambda so Update can wake only its
# own service; the stable /api/wake endpoint retains least privilege to stable.

locals {
  preview_wake_allowed_origins = var.preview_custom_domain != "" ? ["https://${var.preview_custom_domain}"] : ["*"]
  preview_wake_service_arn     = "arn:${data.aws_partition.current.partition}:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${aws_ecs_cluster.main.name}/${local.preview_backend_service_name}"
}

resource "aws_cloudfront_origin_access_control" "preview_wake_backend" {
  count                             = var.enable_preview_backend && var.enable_wake_endpoint ? 1 : 0
  name                              = "${var.project_name}-preview-wake-${var.environment}-oac"
  description                       = "SigV4 access from preview CloudFront to its wake Lambda Function URL"
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "archive_file" "preview_wake_backend" {
  count       = var.enable_preview_backend && var.enable_wake_endpoint ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/.terraform/preview-wake-backend.zip"

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
          return {"Cache-Control": "no-store", "Content-Type": "application/json"}

      def handler(event, context):
          method = event.get("requestContext", {}).get("http", {}).get("method", "POST")
          if method == "OPTIONS":
              return {"statusCode": 204, "headers": _headers(), "body": ""}
          if method != "POST":
              return {"statusCode": 405, "headers": _headers(), "body": json.dumps({"status": "error", "error": "METHOD_NOT_ALLOWED"})}

          service = ecs.describe_services(cluster=CLUSTER_NAME, services=[SERVICE_NAME])["services"][0]
          desired_count = service.get("desiredCount", 0)
          running_count = service.get("runningCount", 0)
          if running_count > 0 and desired_count > 0:
              status = "already_running"
              status_code = 200
          else:
              if desired_count < 1:
                  ecs.update_service(cluster=CLUSTER_NAME, service=SERVICE_NAME, desiredCount=1)
              status = "waking"
              status_code = 202
          return {"statusCode": status_code, "headers": _headers(), "body": json.dumps({"status": status, "cluster": CLUSTER_NAME, "service": SERVICE_NAME})}
    PY
  }
}

resource "aws_iam_role" "preview_wake_backend" {
  count = var.enable_preview_backend && var.enable_wake_endpoint ? 1 : 0
  name  = "${var.project_name}-preview-wake-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "preview_wake_backend" {
  count = var.enable_preview_backend && var.enable_wake_endpoint ? 1 : 0
  name  = "${var.project_name}-preview-wake-${var.environment}"
  role  = aws_iam_role.preview_wake_backend[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ecs:DescribeServices", "ecs:UpdateService"]
      Resource = local.preview_wake_service_arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "preview_wake_backend_basic_execution" {
  count      = var.enable_preview_backend && var.enable_wake_endpoint ? 1 : 0
  role       = aws_iam_role.preview_wake_backend[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "preview_wake_backend" {
  count            = var.enable_preview_backend && var.enable_wake_endpoint ? 1 : 0
  function_name    = "${var.project_name}-preview-wake-${var.environment}"
  role             = aws_iam_role.preview_wake_backend[0].arn
  handler          = "lambda_function.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.preview_wake_backend[0].output_path
  source_code_hash = data.archive_file.preview_wake_backend[0].output_base64sha256
  timeout          = var.wake_endpoint_timeout_seconds

  environment {
    variables = {
      CLUSTER_NAME = aws_ecs_cluster.main.name
      SERVICE_NAME = local.preview_backend_service_name
    }
  }
}

resource "aws_lambda_function_url" "preview_wake_backend" {
  count              = var.enable_preview_backend && var.enable_wake_endpoint ? 1 : 0
  function_name      = aws_lambda_function.preview_wake_backend[0].function_name
  authorization_type = "AWS_IAM"

  cors {
    allow_credentials = false
    allow_headers     = ["content-type", "x-amz-content-sha256"]
    allow_methods     = ["POST"]
    allow_origins     = local.preview_wake_allowed_origins
    max_age           = 300
  }
}

resource "aws_lambda_permission" "preview_wake_backend_function_url" {
  count         = var.enable_preview_backend && var.enable_wake_endpoint ? 1 : 0
  statement_id  = "AllowPreviewCloudFrontFunctionUrlInvoke"
  action        = "lambda:InvokeFunctionUrl"
  function_name = aws_lambda_function.preview_wake_backend[0].function_name
  principal     = "cloudfront.amazonaws.com"
  source_arn    = aws_cloudfront_distribution.preview[0].arn
}

resource "aws_lambda_permission" "preview_wake_backend_function" {
  count         = var.enable_preview_backend && var.enable_wake_endpoint ? 1 : 0
  statement_id  = "AllowPreviewCloudFrontFunctionInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.preview_wake_backend[0].function_name
  principal     = "cloudfront.amazonaws.com"
  source_arn    = aws_cloudfront_distribution.preview[0].arn
}
