# Runbook: Rollback ISLI Deployment

## Scenario

A bad release has caused degraded service. You need to revert ECS task definitions to the previous stable image.

## Quick Rollback (ECS)

### 1. Identify Previous Task Definition

```bash
aws ecs describe-task-definition \
  --task-definition isli-core-api \
  --query 'taskDefinition.previousRevision'
```

### 2. Update Service to Previous Revision

```bash
aws ecs update-service \
  --cluster isli-cluster \
  --service isli-core-api \
  --task-definition isli-core-api:<PREVIOUS_REVISION>
```

Repeat for each affected service (`isli-keeper`, `isli-channels`, `isli-skills`, `isli-board`).

### 3. Wait for Stabilization

```bash
aws ecs wait services-stable \
  --cluster isli-cluster \
  --services isli-core-api isli-keeper isli-channels isli-skills isli-board
```

## Terraform Rollback

If the Terraform apply introduced breaking infrastructure changes:

```bash
cd infra/terraform
terraform plan -var-file="terraform.tfvars" -out=tfplan
tfenv use 1.8.0  # ensure correct version
terraform apply tfplan
```

## Post-Rollback Verification

Run the same smoke tests from [deploy.md](deploy.md).

## Root Cause

After service is stable, investigate the failure via:

- CloudWatch Logs (`/ecs/isli-*`)
- OpenTelemetry traces (Jaeger/Tempo)
- ECS service events (`aws ecs describe-services`)
