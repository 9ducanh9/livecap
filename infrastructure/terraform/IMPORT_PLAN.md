# LiveCap Terraform Import Plan

This checklist reconstructs Terraform state for the existing LiveCap legacy
stack. Import changes state only; it must not be combined with an apply until
the post-import plan has been reviewed.

## Preconditions

1. Create the remote-state bucket from `infrastructure/bootstrap/remote-state`
   only after its four-resource plan is approved.
2. Configure the untracked `backend.hcl`, then run
   `terraform init -reconfigure -backend-config=backend.hcl`. Do not use
   `-migrate-state` because there is no trusted local state to migrate.
3. Set `AWS_PROFILE=livecap-codex`, `AWS_REGION=ap-southeast-1`, and pass the
   immutable backend Git SHA through `-var "backend_image_tag=<GIT_SHA>"`.
4. Run each import once, checking `terraform state show <address>` before
   continuing to the next group.

Risk describes the impact of accepting the first post-import plan, not the
state-only import command itself.

## Import Checklist

| Resource address | Existing AWS identifier | Import command | Risk |
| --- | --- | --- | --- |
| `aws_lb.main` | `arn:aws:elasticloadbalancing:ap-southeast-1:720459752315:loadbalancer/app/livecap-alb-dev/4b4de1301030b116` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_lb.main' 'arn:aws:elasticloadbalancing:ap-southeast-1:720459752315:loadbalancer/app/livecap-alb-dev/4b4de1301030b116'` | High |
| `aws_lb_target_group.backend` | `arn:aws:elasticloadbalancing:ap-southeast-1:720459752315:targetgroup/livecap-backend-tg-dev/f758fd7e5153cc18` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_lb_target_group.backend' 'arn:aws:elasticloadbalancing:ap-southeast-1:720459752315:targetgroup/livecap-backend-tg-dev/f758fd7e5153cc18'` | High |
| `aws_lb_listener.http_dev[0]` | `arn:aws:elasticloadbalancing:ap-southeast-1:720459752315:listener/app/livecap-alb-dev/4b4de1301030b116/9079df2e1255c130` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_lb_listener.http_dev[0]' 'arn:aws:elasticloadbalancing:ap-southeast-1:720459752315:listener/app/livecap-alb-dev/4b4de1301030b116/9079df2e1255c130'` | High |
| `aws_cloudfront_origin_access_control.frontend` | `E3FS507OAK3L7C` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_cloudfront_origin_access_control.frontend' 'E3FS507OAK3L7C'` | Low |
| `aws_cloudfront_distribution.frontend` | `E39ADG0ES17RP1` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_cloudfront_distribution.frontend' 'E39ADG0ES17RP1'` | High |
| `aws_cloudwatch_log_group.backend` | `/ecs/livecap-backend-dev` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_cloudwatch_log_group.backend' '/ecs/livecap-backend-dev'` | Medium |
| `aws_cloudwatch_log_group.alb` | `/aws/alb/livecap-dev` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_cloudwatch_log_group.alb' '/aws/alb/livecap-dev'` | Medium |
| `aws_ecr_repository.backend` | `livecap-backend` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_ecr_repository.backend' 'livecap-backend'` | Medium |
| `aws_ecr_lifecycle_policy.backend` | `livecap-backend` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_ecr_lifecycle_policy.backend' 'livecap-backend'` | Medium |
| `aws_ecs_cluster.main` | `livecap-cluster-dev` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_ecs_cluster.main' 'livecap-cluster-dev'` | Medium |
| `aws_ecs_task_definition.backend` | `arn:aws:ecs:ap-southeast-1:720459752315:task-definition/livecap-backend-dev:5` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_ecs_task_definition.backend' 'arn:aws:ecs:ap-southeast-1:720459752315:task-definition/livecap-backend-dev:5'` | High |
| `aws_ecs_service.backend` | `livecap-cluster-dev/livecap-backend-service-dev` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_ecs_service.backend' 'livecap-cluster-dev/livecap-backend-service-dev'` | High |
| `aws_appautoscaling_target.ecs_target` | `ecs/service/livecap-cluster-dev/livecap-backend-service-dev/ecs:service:DesiredCount` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_appautoscaling_target.ecs_target' 'ecs/service/livecap-cluster-dev/livecap-backend-service-dev/ecs:service:DesiredCount'` | Medium |
| `aws_appautoscaling_policy.ecs_cpu_policy` | `ecs/service/livecap-cluster-dev/livecap-backend-service-dev/ecs:service:DesiredCount/livecap-cpu-autoscaling-dev` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_appautoscaling_policy.ecs_cpu_policy' 'ecs/service/livecap-cluster-dev/livecap-backend-service-dev/ecs:service:DesiredCount/livecap-cpu-autoscaling-dev'` | Medium |
| `aws_appautoscaling_policy.ecs_memory_policy` | `ecs/service/livecap-cluster-dev/livecap-backend-service-dev/ecs:service:DesiredCount/livecap-memory-autoscaling-dev` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_appautoscaling_policy.ecs_memory_policy' 'ecs/service/livecap-cluster-dev/livecap-backend-service-dev/ecs:service:DesiredCount/livecap-memory-autoscaling-dev'` | Medium |
| `aws_iam_role.ecs_task_execution` | `livecap-ecs-task-execution-dev` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_iam_role.ecs_task_execution' 'livecap-ecs-task-execution-dev'` | Low |
| `aws_iam_role_policy_attachment.ecs_task_execution_policy` | `livecap-ecs-task-execution-dev/arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_iam_role_policy_attachment.ecs_task_execution_policy' 'livecap-ecs-task-execution-dev/arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy'` | Low |
| `aws_iam_role.ecs_task` | `livecap-ecs-task-dev` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_iam_role.ecs_task' 'livecap-ecs-task-dev'` | Low |
| `aws_iam_role_policy.transcript_bucket_access` | `livecap-ecs-task-dev:livecap-transcript-bucket-access` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_iam_role_policy.transcript_bucket_access' 'livecap-ecs-task-dev:livecap-transcript-bucket-access'` | Medium |
| `aws_iam_role_policy.transcribe_access` | `livecap-ecs-task-dev:livecap-transcribe-access` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_iam_role_policy.transcribe_access' 'livecap-ecs-task-dev:livecap-transcribe-access'` | Medium |
| `aws_iam_role_policy.translate_access` | `livecap-ecs-task-dev:livecap-translate-access` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_iam_role_policy.translate_access' 'livecap-ecs-task-dev:livecap-translate-access'` | Medium |
| `aws_iam_role_policy.cloudwatch_logs_access` | `livecap-ecs-task-dev:livecap-cloudwatch-logs-access` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_iam_role_policy.cloudwatch_logs_access' 'livecap-ecs-task-dev:livecap-cloudwatch-logs-access'` | Medium |
| `aws_s3_bucket.frontend` | `livecap-frontend-dev-720459752315` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_s3_bucket.frontend' 'livecap-frontend-dev-720459752315'` | Low |
| `aws_s3_bucket_public_access_block.frontend` | `livecap-frontend-dev-720459752315` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_s3_bucket_public_access_block.frontend' 'livecap-frontend-dev-720459752315'` | Low |
| `aws_s3_bucket_versioning.frontend` | `livecap-frontend-dev-720459752315` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_s3_bucket_versioning.frontend' 'livecap-frontend-dev-720459752315'` | Low |
| `aws_s3_bucket_policy.frontend_cloudfront_access` | `livecap-frontend-dev-720459752315` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_s3_bucket_policy.frontend_cloudfront_access' 'livecap-frontend-dev-720459752315'` | High |
| `aws_s3_bucket_server_side_encryption_configuration.frontend` | `livecap-frontend-dev-720459752315` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_s3_bucket_server_side_encryption_configuration.frontend' 'livecap-frontend-dev-720459752315'` | Low |
| `aws_s3_bucket.transcript` | `livecap-transcripts-dev-720459752315` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_s3_bucket.transcript' 'livecap-transcripts-dev-720459752315'` | Low |
| `aws_s3_bucket_public_access_block.transcript` | `livecap-transcripts-dev-720459752315` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_s3_bucket_public_access_block.transcript' 'livecap-transcripts-dev-720459752315'` | Low |
| `aws_s3_bucket_versioning.transcript` | `livecap-transcripts-dev-720459752315` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_s3_bucket_versioning.transcript' 'livecap-transcripts-dev-720459752315'` | Low |
| `aws_s3_bucket_lifecycle_configuration.transcript_retention` | `livecap-transcripts-dev-720459752315` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_s3_bucket_lifecycle_configuration.transcript_retention' 'livecap-transcripts-dev-720459752315'` | Medium |
| `aws_s3_bucket_server_side_encryption_configuration.transcript` | `livecap-transcripts-dev-720459752315` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_s3_bucket_server_side_encryption_configuration.transcript' 'livecap-transcripts-dev-720459752315'` | Low |
| `aws_security_group.alb` | `sg-0c9fd0d5b64ae8e61` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_security_group.alb' 'sg-0c9fd0d5b64ae8e61'` | High |
| `aws_security_group.ecs_tasks` | `sg-0391c85bb86d6161e` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_security_group.ecs_tasks' 'sg-0391c85bb86d6161e'` | High |
| `aws_cloudfront_function.spa_rewrite` | `livecap-spa-rewrite-dev` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_cloudfront_function.spa_rewrite' 'livecap-spa-rewrite-dev'` | Medium |
| `aws_wafv2_web_acl.cloudfront[0]` | `ee59d195-d631-4c82-8563-358a8fbd6662/livecap-cloudfront-waf-dev/CLOUDFRONT` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_wafv2_web_acl.cloudfront[0]' 'ee59d195-d631-4c82-8563-358a8fbd6662/livecap-cloudfront-waf-dev/CLOUDFRONT'` | High |
| `aws_wafv2_web_acl.alb[0]` | `409d74dd-0f9c-43a1-a82a-e5230b84080e/livecap-alb-waf-dev/REGIONAL` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_wafv2_web_acl.alb[0]' '409d74dd-0f9c-43a1-a82a-e5230b84080e/livecap-alb-waf-dev/REGIONAL'` | High |
| `aws_wafv2_web_acl_association.alb[0]` | Existing ALB/WAF association | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_wafv2_web_acl_association.alb[0]' 'arn:aws:wafv2:ap-southeast-1:720459752315:regional/webacl/livecap-alb-waf-dev/409d74dd-0f9c-43a1-a82a-e5230b84080e,arn:aws:elasticloadbalancing:ap-southeast-1:720459752315:loadbalancer/app/livecap-alb-dev/4b4de1301030b116'` | High |
| `aws_cloudwatch_log_group.cloudfront_waf[0]` | `aws-waf-logs-livecap-cloudfront-dev` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_cloudwatch_log_group.cloudfront_waf[0]' 'aws-waf-logs-livecap-cloudfront-dev'` | Low |
| `aws_cloudwatch_log_group.alb_waf[0]` | `aws-waf-logs-livecap-alb-dev` | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_cloudwatch_log_group.alb_waf[0]' 'aws-waf-logs-livecap-alb-dev'` | Low |
| `aws_wafv2_web_acl_logging_configuration.cloudfront[0]` | CloudFront WAF ARN | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_wafv2_web_acl_logging_configuration.cloudfront[0]' 'arn:aws:wafv2:us-east-1:720459752315:global/webacl/livecap-cloudfront-waf-dev/ee59d195-d631-4c82-8563-358a8fbd6662'` | Medium |
| `aws_wafv2_web_acl_logging_configuration.alb[0]` | ALB WAF ARN | `terraform import -var "backend_image_tag=<GIT_SHA>" 'aws_wafv2_web_acl_logging_configuration.alb[0]' 'arn:aws:wafv2:ap-southeast-1:720459752315:regional/webacl/livecap-alb-waf-dev/409d74dd-0f9c-43a1-a82a-e5230b84080e'` | Medium |

Replace only `<GIT_SHA>` with the immutable image tag selected for deployment.

## Known Post-import Drift

- ECS Container Insights is enabled in AWS but disabled in Terraform.
- Legacy ECS autoscaling is `min=1, max=2`; Terraform constrains it to
  `min=1, max=1` during the rollback window.
- Backend, ALB, and WAF log groups use 14-day retention.
- Transcript lifecycle expiration is already 14 days.
- ECR is immutable and contains `1ef4250` and architecture-specific
  `1ef4250-amd64` tags.
- CloudFront and ALB blocking WAFs, the CloudFront SPA rewrite function,
  origin verification header, CloudFront-only ALB ingress, and filtered WAF
  logging already exist and must be imported before planning.
- The `api.livecap.logantai.com` ACM certificate in `ap-southeast-1` is issued
  and is passed as a variable for the target ALB; it is not managed here.
- The current ECS task uses public subnets and a public IP. The target service
  is created separately in private subnets; the legacy service remains for
  rollback.

## Validated Sandbox Plan

All 34 import commands were validated on 2026-07-02 against a temporary local
state. No remote state or AWS resource was modified. The resulting plan was:

```text
Plan: 33 to add, 18 to change, 1 to destroy.
```

The 33 creates are the target VPC, subnets, routes, one NAT Gateway, target
ALB/target group/listener, private target ECS service/task definition,
target autoscaling, WAF ACLs/associations, dashboard, and the idle scale-down
IAM policy.

The 18 in-place changes include:

- Disable Container Insights on the existing ECS cluster.
- Constrain legacy ECS autoscaling from `max=2` to `max=1`.
- Set backend and ALB placeholder log retention to 14 days.
- Change transcript expiration from 30 to 14 days.
- Change ECR tag mutability from `MUTABLE` to `IMMUTABLE`.
- Add the target ALB origin and WAF association to CloudFront while keeping
  `route_backend_to_target=false`.
- Reconcile tags and non-routing metadata on imported legacy resources. The
  deployment circuit breaker/rollback is enabled on the new target ECS service,
  not retrofitted onto the rollback service.

The single destroy is the destroy half of replacing
`aws_ecr_lifecycle_policy.backend`. It deletes and recreates only the ECR
lifecycle policy; it does not delete the repository or images. It remains a
review gate because the new policy changes retention from tagged `v*` images
to the latest 20 immutable tagged images.

Treat any replacement or deletion of an imported legacy resource as a stop
condition. The expected migration plan may create target resources and update
selected legacy settings in place, but it must not destroy the current path.

## Explicitly Excluded

Do not import or delete these resources in this migration:

- Default VPC `vpc-05e68804de2912d90`, its default subnets, and Internet
  Gateway. Terraform reads them as data sources for the legacy stack.
- Stopped EC2 instance `i-08aff98329bf8add2`, its 8 GiB EBS volume, and
  `LiveCapEC2Role`.
- Legacy S3 bucket `livecaptranscripts`.
- Container Insights generated log group. It is controlled through the ECS
  cluster setting, not a standalone Terraform log-group resource.

Ownership of excluded resources must be confirmed before a separate import or
decommission plan is prepared.
