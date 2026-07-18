# Frontend Environments

LiveCap uses two isolated static frontend environments:

| Environment | Source branch | S3 bucket | Entry URL | Purpose |
| --- | --- | --- | --- | --- |
| Stable | `main` | `livecap-frontend-dev-<account-id>` | `https://dpeohr327wt9l.cloudfront.net` | The working MVP that reviewers can use. |
| Preview | `Update` | `livecap-frontend-preview-dev-<account-id>` | `https://livecap.logantai.com` | Review and test product changes before merging. |

The two distributions proxy `/api/*`, `/ws/*`, and `/api/wake` to the same
current backend. This is deliberate for frontend iteration. A breaking backend
change needs its own preview backend before it is exposed through Preview.

## Domain cutover sequence

CloudFront allows an alternate domain name on only one distribution at a time.
Use the three reviewed Terraform phases below. Do not upload builds to the
stable bucket from `Update`.

1. Set `enable_preview_frontend=true` with `preview_custom_domain=""` and apply.
   Upload a build from `Update` to the preview bucket; test the generated
   CloudFront URL.
2. Set `detach_custom_domain_from_stable=true`; apply and wait for the stable
   distribution to finish deploying. The stable CloudFront URL remains usable.
3. Set `preview_custom_domain="livecap.logantai.com"`; apply, then point the
   DNS CNAME to the preview distribution domain name.

Build/deploy commands must select their destination deliberately:

```powershell
# Stable release: build from main, then upload only to the stable bucket.
# Preview release: build from Update, then upload only to the preview bucket.
aws s3 sync frontend/dist/ s3://<selected-bucket>/ --delete
aws cloudfront create-invalidation --distribution-id <selected-distribution-id> --paths "/*"
```

CloudFront invalidation does not deploy code by itself. It only clears cache for
the distribution whose bucket has already been updated.
