# Branded Cognito verification/reset emails (logo + custom copy) via a
# Custom Message Lambda trigger. The built-in verification_message_template
# in cognito.tf only supports plain text, so HTML (and the logo image) has to
# come from here. Cognito falls back to that plain-text template for any
# trigger source this Lambda doesn't recognize.

locals {
  cognito_email_logo_url = "${local.frontend_base_url}/logo-email.png"
}

data "archive_file" "cognito_custom_message" {
  count       = var.enable_cognito_auth ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/.terraform/cognito-custom-message.zip"

  source {
    filename = "lambda_function.py"
    content  = <<-PY
      import os

      LOGO_URL = os.environ.get("LOGO_URL", "")
      BRAND_NAME = os.environ.get("BRAND_NAME", "LiveCap")

      # (email subject, message title, body copy, footer copy) per trigger source.
      # {brand} is substituted below; the literal {{####}} placeholder is left
      # intact for Cognito to replace with the real code.
      _COPY = {
          "SignUp": (
              "Confirm your {brand} account",
              "Verify your email",
              "Welcome to {brand}! Enter this code to confirm your account. It expires in 24 hours.",
              "If you didn't create a {brand} account, you can safely ignore this email.",
          ),
          "ResendCode": (
              "Confirm your {brand} account",
              "Verify your email",
              "Here is your new verification code. Enter it to confirm your {brand} account. It expires in 24 hours.",
              "If you didn't request this code, you can safely ignore this email.",
          ),
          "ForgotPassword": (
              "Reset your {brand} password",
              "Reset your password",
              "We received a request to reset your {brand} password. Enter this code to continue. It expires in 1 hour.",
              "If you didn't request a password reset, you can safely ignore this email and your password will stay the same.",
          ),
          "UpdateUserAttribute": (
              "Confirm your new email for {brand}",
              "Verify your new email",
              "Enter this code to confirm your new email address on {brand}.",
              "If you didn't request this change, please secure your account.",
          ),
          "VerifyUserAttribute": (
              "Confirm your email for {brand}",
              "Verify your email",
              "Enter this code to verify your email address on {brand}.",
              "If you didn't request this, you can safely ignore this email.",
          ),
      }


      def _html(title, body_text, footer_text):
          logo_block = (
              '<img src="' + LOGO_URL + '" width="56" height="56" alt="' + BRAND_NAME + '" '
              'style="display:block;margin:0 auto;border-radius:50%;" />'
              if LOGO_URL
              else ""
          )
          return f"""
          <div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background-color:#f7f8fc;padding:32px 16px;">
            <div style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e6e8f0;">
              <div style="background-color:#102247;padding:28px 24px;text-align:center;">
                {logo_block}
                <div style="color:#ffffff;font-size:18px;font-weight:700;margin-top:10px;letter-spacing:0.02em;">{BRAND_NAME}</div>
              </div>
              <div style="padding:32px 24px;">
                <h1 style="margin:0 0 12px;color:#102247;font-size:20px;">{title}</h1>
                <p style="margin:0 0 24px;color:#4b5568;font-size:15px;line-height:1.6;">{body_text}</p>
                <div style="background-color:#f7f8fc;border:1px dashed #0a9c88;border-radius:12px;padding:16px;text-align:center;margin-bottom:24px;">
                  <span style="font-size:28px;font-weight:700;letter-spacing:0.3em;color:#0a9c88;">{{####}}</span>
                </div>
                <p style="margin:0;color:#8a92a6;font-size:13px;line-height:1.5;">{footer_text}</p>
              </div>
            </div>
            <p style="text-align:center;color:#a3aabb;font-size:12px;margin-top:20px;">&copy; {BRAND_NAME} &middot; Real-time captions for every conversation</p>
          </div>
          """.strip()


      def handler(event, context):
          trigger_key = event.get("triggerSource", "").replace("CustomMessage_", "")
          copy = _COPY.get(trigger_key)
          if copy is None:
              return event

          subject_tpl, title, body_tpl, footer_tpl = copy
          event["response"]["emailSubject"] = subject_tpl.format(brand=BRAND_NAME)
          event["response"]["emailMessage"] = _html(
              title,
              body_tpl.format(brand=BRAND_NAME),
              footer_tpl.format(brand=BRAND_NAME),
          )
          return event
    PY
  }
}

resource "aws_iam_role" "cognito_custom_message" {
  count = var.enable_cognito_auth ? 1 : 0
  name  = "${var.project_name}-cognito-custom-message-${var.environment}"

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

resource "aws_iam_role_policy_attachment" "cognito_custom_message_basic_execution" {
  count      = var.enable_cognito_auth ? 1 : 0
  role       = aws_iam_role.cognito_custom_message[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "cognito_custom_message" {
  count = var.enable_cognito_auth ? 1 : 0

  function_name    = "${var.project_name}-cognito-custom-message-${var.environment}"
  role             = aws_iam_role.cognito_custom_message[0].arn
  handler          = "lambda_function.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.cognito_custom_message[0].output_path
  source_code_hash = data.archive_file.cognito_custom_message[0].output_base64sha256
  timeout          = 5

  environment {
    variables = {
      LOGO_URL   = local.cognito_email_logo_url
      BRAND_NAME = "LiveCap"
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.cognito_custom_message_basic_execution,
  ]
}

resource "aws_lambda_permission" "cognito_custom_message" {
  count = var.enable_cognito_auth ? 1 : 0

  statement_id  = "AllowCognitoInvokeCustomMessage"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cognito_custom_message[0].function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.livecap[0].arn
}
