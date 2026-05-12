# Runbook: Deploy ISLI to Production

## Prerequisites

- AWS CLI configured with appropriate credentials
- Terraform >= 1.8.0 installed
- Access to the `isli-terraform-state` S3 bucket
- Docker images pushed to GHCR (`ghcr.io/isli-ai/*`)

## Steps

### 1. Validate Terraform

```bash
cd infra/terraform
terraform init
terraform validate
terraform plan
```

### 2. Set Required Variables

Create or update `terraform.tfvars`:

```hcl
aws_region         = "eu-west-1"
db_password        = "YOUR_STRONG_PASSWORD"
core_api_image     = "ghcr.io/isli-ai/isli-core:SHA"
keeper_image       = "ghcr.io/isli-ai/isli-keeper:SHA"
channels_image     = "ghcr.io/isli-ai/isli-channels:SHA"
skills_image       = "ghcr.io/isli-ai/isli-skills:SHA"
board_image        = "ghcr.io/isli-ai/isli-board:SHA"
```

### 3. Apply Infrastructure

```bash
terraform apply -var-file="terraform.tfvars"
```

### 4. Verify Deployment

Wait for ECS services to stabilize:

```bash
aws ecs wait services-stable \
  --cluster isli-cluster \
  --services $(aws ecs list-services --cluster isli-cluster --query 'serviceArns[*]' --output text)
```

### 5. Smoke Tests

```bash
ALB_DNS=$(terraform output -raw alb_dns_name)
curl -sf http://${ALB_DNS}/health
curl -sf http://${ALB_DNS}/ready
curl -sf http://${ALB_DNS}/api/health
curl -sf http://${ALB_DNS}/keeper/health
curl -sf http://${ALB_DNS}/channels/health
curl -sf http://${ALB_DNS}/skills/health
```

## Rollback

See [rollback.md](rollback.md).
