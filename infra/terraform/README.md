# Optional AWS Deployment

This Terraform configuration deploys ISLI to AWS ECS Fargate. It is **optional** and not required for the primary Docker Compose deployment path.

## Requirements

- AWS account and credentials
- Terraform >= 1.8.0
- AWS CLI configured with appropriate IAM permissions

## Usage

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

## State

The backend is configured to use S3. Update `backend.tf` or pass `-backend-config` with your own bucket.

## Notes

- The Docker Compose files in the project root are the canonical deployment method for VPS and PCs.
- Use this Terraform only if you specifically need AWS-managed infrastructure.
