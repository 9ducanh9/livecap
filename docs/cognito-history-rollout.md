# Cognito and Transcript History Rollout

This runbook enables the optional product-account feature introduced in C5. It
does not store raw audio. Cognito identifies the browser user, DynamoDB stores
only owner-scoped export metadata, and the transcript body remains a private
TXT object in the existing S3 transcript bucket under an owner-specific prefix.

## Preconditions

- Deploy from the `Update` branch only after code review.
- Choose the exact production callback and sign-out URL, including `/app`.
- Choose a globally unique Cognito Hosted UI domain prefix.
- Keep the existing 14-day S3 lifecycle; set the history metadata retention to
  the same period unless a separate privacy review approves a longer history.

## Terraform configuration

Add only untracked values to `terraform.tfvars`:

```hcl
enable_cognito_auth              = true
cognito_callback_urls            = ["https://livecap.example.com/app", "http://localhost:5173/app"]
cognito_logout_urls              = ["https://livecap.example.com/app", "http://localhost:5173/app"]
cognito_domain_prefix            = "livecap-example-dev"
transcript_history_retention_days = 14
```

Run `terraform plan` and review the User Pool, public browser client, hosted
UI domain, history table, and task-role permissions. A human must run apply.
The browser client has no client secret because it uses Authorization Code with
PKCE; do not add one to Vite environment files.

## Frontend build configuration

After apply, use Terraform outputs to set build-time values outside Git:

```dotenv
VITE_AUTH_ENABLED=true
VITE_COGNITO_DOMAIN=<hosted-ui-domain>
VITE_COGNITO_CLIENT_ID=<cognito-web-client-id>
VITE_COGNITO_REDIRECT_URI=https://livecap.example.com/app
```

Rebuild and deploy the frontend together with a backend image that includes
the C5 routes. The backend container receives the User Pool ID, history table
name, and `ENABLE_AUTH=true` from Terraform.

## Verification

1. Sign in through the Hosted UI and return to `/app`.
2. Start a WebSocket session. A token is negotiated through
   `Sec-WebSocket-Protocol`, not a URL query string.
3. Export a non-empty transcript; verify the TXT downloads and a metadata row
   appears only under the signed-in user's DynamoDB partition.
4. Refresh the app and download the item from Transcript history.
5. Verify another Cognito user receives neither list nor download access to the
   first user's item.
6. Verify an unauthenticated WebSocket and API history request are rejected
   when `ENABLE_AUTH=true`.
7. Verify the S3 lifecycle and DynamoDB TTL remove data after 14 days.

## Rollback

Set `enable_cognito_auth=false`, review plan, and apply. The backend resumes
anonymous MVP behaviour and does not read history. Do not delete the User Pool
or history table until the retention window and ownership review are complete.
