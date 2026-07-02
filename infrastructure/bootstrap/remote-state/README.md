# LiveCap Terraform Remote State Bootstrap

This bootstrap stack creates the S3 bucket used by the main LiveCap Terraform
state backend in `ap-southeast-1`. It is intentionally separate from
`infrastructure/terraform`.

## Review-gated workflow

```powershell
cd infrastructure/bootstrap/remote-state
terraform init
terraform plan
```

Run `terraform apply` only after reviewing the plan. Then copy the output bucket
name into a local, untracked `infrastructure/terraform/backend.hcl` file:

```hcl
bucket = "livecap-terraform-state-dev-123456789012"
```

The main stack uses:

```powershell
cd ../../terraform
terraform init -backend-config=backend.hcl
terraform plan
```

Do not run `terraform init -migrate-state` until the migration plan has been
reviewed. The main backend uses S3 native lockfiles, so Terraform 1.10 or newer
is required. If an older Terraform version must be used, replace the lockfile
setting with a reviewed DynamoDB lock-table design before migration.
