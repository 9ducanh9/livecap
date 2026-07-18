# LiveCap branding for the Cognito classic Hosted UI (login page).
#
# Styles the hosted sign-in page (see hosted-ui/login.css) to match the app's
# emerald/ink palette. Applies only when Cognito auth + a hosted domain exist.
# Cognito validates the CSS against its supported "-customizable" selectors; a
# rejected rule fails apply — remove that property and retry.
#
# Quick manual apply to a LIVE user pool without a full plan/apply:
#   aws cognito-idp set-ui-customization \
#     --user-pool-id <POOL_ID> --client-id <WEB_CLIENT_ID> \
#     --css file://infrastructure/terraform/hosted-ui/login.css

resource "aws_cognito_user_pool_ui_customization" "hosted_ui" {
  count = var.enable_cognito_auth && trimspace(var.cognito_domain_prefix) != "" ? 1 : 0

  user_pool_id = aws_cognito_user_pool.livecap[0].id
  client_id    = aws_cognito_user_pool_client.web[0].id
  css          = file("${path.module}/hosted-ui/login.css")

  depends_on = [aws_cognito_user_pool_domain.hosted_ui]
}
