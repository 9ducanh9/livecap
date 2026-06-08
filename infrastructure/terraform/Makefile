# Makefile for LiveCap Infrastructure Management

.PHONY: help init plan apply destroy clean validate fmt push-backend-image deploy-backend deploy-frontend deploy-all

# Default target
help:
	@echo "LiveCap Infrastructure Management"
	@echo "=================================="
	@echo ""
	@echo "Terraform Commands:"
	@echo "  make init             - Initialize Terraform"
	@echo "  make validate         - Validate Terraform configuration"
	@echo "  make fmt              - Format Terraform files"
	@echo "  make plan             - Show execution plan"
	@echo "  make apply            - Apply infrastructure changes"
	@echo "  make destroy          - Destroy all infrastructure"
	@echo "  make clean            - Clean Terraform cache and state"
	@echo ""
	@echo "Deployment Commands:"
	@echo "  make push-backend-image - Build and push backend Docker image only"
	@echo "  make deploy-backend   - Build and push backend Docker image"
	@echo "  make deploy-frontend  - Build and deploy frontend to S3"
	@echo "  make deploy-all       - Deploy both backend and frontend"
	@echo ""
	@echo "Utility Commands:"
	@echo "  make outputs          - Show Terraform outputs"
	@echo "  make logs             - Tail backend application logs"
	@echo "  make status           - Show ECS service status"
	@echo "  make invalidate-cdn   - Invalidate CloudFront cache"

# Initialize Terraform
init:
	terraform init

# Validate configuration
validate:
	terraform validate

# Format Terraform files
fmt:
	terraform fmt -recursive

# Show execution plan
plan:
	terraform plan

# Apply infrastructure changes
apply:
	terraform apply

# Destroy infrastructure
destroy:
	@echo "WARNING: This will destroy all resources!"
	@echo "Emptying S3 buckets first..."
	aws s3 rm s3://$$(terraform output -raw frontend_bucket_name) --recursive || true
	aws s3 rm s3://$$(terraform output -raw transcript_bucket_name) --recursive || true
	terraform destroy

# Clean Terraform cache
clean:
	rm -rf .terraform
	rm -f .terraform.lock.hcl
	rm -f terraform.tfstate.backup

# Show outputs
outputs:
	terraform output

# Build and push backend Docker image without touching ECS service.
# Use this during first-time deployment after creating the ECR repository.
push-backend-image:
	@echo "Building and pushing backend Docker image..."
	@aws ecr get-login-password --region $$(terraform output -raw region) | \
		docker login --username AWS --password-stdin $$(terraform output -raw ecr_repository_uri)
	@cd ../../backend && docker build -t livecap-backend .
	@docker tag livecap-backend:latest $$(terraform output -raw ecr_repository_uri):latest
	@docker push $$(terraform output -raw ecr_repository_uri):latest

# Deploy backend Docker image and force ECS service to pull it.
# Use this only after the ECS service has already been created.
deploy-backend: push-backend-image
	@echo "Forcing ECS service update..."
	@aws ecs update-service \
		--cluster $$(terraform output -raw ecs_cluster_name) \
		--service $$(terraform output -raw ecs_service_name) \
		--force-new-deployment \
		--region $$(terraform output -raw region)
	@echo "Backend deployment initiated!"

# Deploy frontend to S3
deploy-frontend:
	@echo "Building frontend..."
	@cd ../../frontend && \
		printf "VITE_API_BASE_URL=%s\nVITE_WS_URL=%s\n" \
			"$$(cd ../infrastructure/terraform && terraform output -raw alb_backend_base_url)" \
			"$$(cd ../infrastructure/terraform && terraform output -raw alb_websocket_url)" > .env.production && \
		npm run build
	@echo "Uploading to S3..."
	@aws s3 sync ../../frontend/dist/ s3://$$(terraform output -raw frontend_bucket_name)/ --delete
	@echo "Invalidating CloudFront cache..."
	@aws cloudfront create-invalidation \
		--distribution-id $$(terraform output -raw cloudfront_distribution_id) \
		--paths "/*" \
		--region $$(terraform output -raw region)
	@echo "Frontend deployment complete!"
	@echo "Frontend URL: $$(terraform output -raw cloudfront_url)"

# Deploy both backend and frontend
deploy-all: deploy-backend deploy-frontend
	@echo ""
	@echo "Full deployment complete!"
	@echo "Frontend: $$(terraform output -raw cloudfront_url)"
	@echo "Backend API: $$(terraform output -raw alb_backend_base_url)"

# Tail backend logs
logs:
	@echo "Tailing backend logs (Ctrl+C to exit)..."
	@aws logs tail $$(terraform output -raw cloudwatch_log_group_name) --follow --region $$(terraform output -raw region)

# Show ECS service status
status:
	@echo "ECS Service Status:"
	@aws ecs describe-services \
		--cluster $$(terraform output -raw ecs_cluster_name) \
		--services $$(terraform output -raw ecs_service_name) \
		--region $$(terraform output -raw region) \
		--query 'services[0].{Status:status,DesiredCount:desiredCount,RunningCount:runningCount,PendingCount:pendingCount}' \
		--output table

# Invalidate CloudFront cache
invalidate-cdn:
	@echo "Invalidating CloudFront cache..."
	@aws cloudfront create-invalidation \
		--distribution-id $$(terraform output -raw cloudfront_distribution_id) \
		--paths "/*" \
		--region $$(terraform output -raw region)
	@echo "Cache invalidation initiated!"
