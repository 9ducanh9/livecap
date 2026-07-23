# Stable And Preview Runtime Environments

LiveCap keeps the public demonstration and the Update preview isolated without
duplicating the VPC, ALB, ECR repository, or shared observability resources.

| Environment | Frontend | Backend | Authentication |
| --- | --- | --- | --- |
| Stable (`main`) | Stable CloudFront distribution | `livecap-target-service-dev` | Anonymous by default |
| Preview (`Update`) | Preview CloudFront distribution | `livecap-preview-service-dev` | Optional Cognito enforcement |

The ALB default action remains the stable target group. CloudFront removes the
viewer `Host` header when forwarding to an origin, so the preview distribution
adds `X-LiveCap-Environment: preview` as an internal origin header. The ALB
listener rule matches that header and sends only preview API and WebSocket
requests to the preview target group. This header is combined with the existing
CloudFront-origin verification header required by the ALB WAF.

Each service has its own ECS task definition and service name. Its wake Lambda
has only `ecs:DescribeServices` and `ecs:UpdateService` on that one service.
The task's idle scaler therefore scales down only the environment that owns the
last session. Both services remain capped at one task until multi-task support
has completed its load-test gate.

## Rollout Order

1. **Phase 1:** keep `preview_custom_domain = ""` and
   `detach_custom_domain_from_stable = false`. Create the isolated preview
   service and distribution, then record its generated `*.cloudfront.net` URL.
2. Keep `stable_enable_auth_runtime = false`. The stable task rolls back to its
   main image and remains anonymous.
3. Add the generated preview `/app` URL and the intended custom preview URL to
   Cognito callback/logout URLs. Build the Update frontend with public Cognito
   `VITE_*` values, upload it only to the preview S3 bucket, and invalidate only
   the preview distribution.
4. Run a signed-in preview capture, then verify that the stable CloudFront URL
   still accepts an anonymous session.
5. **Phase 2:** set `detach_custom_domain_from_stable = true` and apply the
   stable distribution update. Wait until it deploys.
6. **Phase 3:** point the DNS CNAME for the custom hostname to the generated
   preview distribution domain. Then set `preview_custom_domain`, apply the
   preview distribution change, and validate the custom URL.

The relevant Terraform values live in untracked environment tfvars. Do not put
Cognito secrets or origin verification secrets in tracked files.
