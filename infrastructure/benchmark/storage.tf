resource "aws_ecr_repository" "benchmark" {
  name                 = "${local.prefix}-backend"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_s3_bucket" "benchmark" {
  bucket        = "${local.prefix}-transcripts-${var.expected_account_id}"
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "benchmark" {
  bucket                  = aws_s3_bucket.benchmark.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "benchmark" {
  bucket = aws_s3_bucket.benchmark.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "benchmark" {
  bucket = aws_s3_bucket.benchmark.id
  rule {
    id     = "benchmark-retention"
    status = "Enabled"
    filter {}
    expiration { days = 3 }
  }
}
locals {
  tables = {
    sessions           = { pk = "pk", sk = null, ttl = "expires_at" }
    usage              = { pk = "pk", sk = "sk", ttl = "expires_at" }
    transcript-history = { pk = "user_id", sk = "history_id", ttl = "expires_at" }
    room-events        = { pk = "room_code", sk = "record_key", ttl = "expires_at" }
    admin-audit        = { pk = "pk", sk = "sk", ttl = "ttl" }
  }
}
resource "aws_dynamodb_table" "benchmark" {
  for_each     = local.tables
  name         = "${local.prefix}-${each.key}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = each.value.pk
  range_key    = each.value.sk
  attribute {
    name = each.value.pk
    type = "S"
  }
  dynamic "attribute" {
    for_each = each.value.sk == null ? [] : [each.value.sk]
    content {
      name = attribute.value
      type = "S"
    }
  }
  ttl {
    attribute_name = each.value.ttl
    enabled        = true
  }
}
resource "aws_cognito_user_pool" "benchmark" {
  name                     = "${local.prefix}-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  admin_create_user_config { allow_admin_create_user_only = true }
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }
}
resource "aws_cognito_user_pool_client" "benchmark" {
  name                                 = "${local.prefix}-client"
  user_pool_id                         = aws_cognito_user_pool.benchmark.id
  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  explicit_auth_flows                  = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "aws.cognito.signin.user.admin"]
  callback_urls                        = ["http://localhost:5173/app"]
  logout_urls                          = ["http://localhost:5173/app"]
  supported_identity_providers         = ["COGNITO"]
}
resource "aws_cognito_user_pool_domain" "benchmark" {
  domain       = "${local.prefix}-${var.expected_account_id}"
  user_pool_id = aws_cognito_user_pool.benchmark.id
}
# Reserve a CONFIG namespace without introducing any secret into plan/state.
# Optional Stripe/DeepSeek credentials are absent and their features are off.
resource "aws_ssm_parameter" "benchmark" {
  name  = "/livecap/benchmark/config/environment"
  type  = "String"
  value = "benchmark"
}
