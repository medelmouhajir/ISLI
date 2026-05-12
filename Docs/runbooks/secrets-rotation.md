# Runbook: Secrets Rotation

## Overview

This runbook covers rotation of `JWT_SECRET` and `PII_ENCRYPTION_KEY` without service disruption.

## JWT Secret Rotation

### 1. Generate New Secret

```bash
NEW_JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
echo "$NEW_JWT_SECRET"
```

Minimum 32 bytes. Prefer 48+ bytes.

### 2. Update Secrets Manager (or `.env.production`)

If using AWS Secrets Manager:

```bash
aws secretsmanager put-secret-value \
  --secret-id isli/jwt-secret \
  --secret-string "$NEW_JWT_SECRET"
```

### 3. Rolling Deploy

Deploy the new secret to ECS by updating the task definition environment variable and performing a rolling update. ECS will start new tasks with the new secret before stopping old ones.

```bash
aws ecs update-service \
  --cluster isli-cluster \
  --service isli-core-api \
  --force-new-deployment
```

### 4. Invalidate Old Tokens

Old tokens signed with the previous secret will fail validation after all tasks have rolled. There is no active invalidation step; natural expiry handles cleanup.

## PII Encryption Key Rotation

**Warning:** `PII_ENCRYPTION_KEY` is used for AES-256-GCM encryption of PII data. Changing it without re-encrypting existing data will make that data unreadable.

### 1. Backup Current Key

```bash
aws secretsmanager get-secret-value \
  --secret-id isli/pii-encryption-key \
  --query 'SecretString' --output text > pii-key-backup-$(date +%Y%m%d).txt
```

### 2. Generate New Key

```bash
NEW_PII_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
echo "$NEW_PII_KEY"
```

### 3. Re-Encrypt Existing Data (if any)

If the system has encrypted PII records, run the re-encryption script before switching the active key:

```bash
# Pseudocode — implement based on your encryption module
python scripts/reencrypt_pii.py --old-key-file pii-key-backup-*.txt --new-key "$NEW_PII_KEY"
```

### 4. Update Active Key

```bash
aws secretsmanager put-secret-value \
  --secret-id isli/pii-encryption-key \
  --secret-string "$NEW_PII_KEY"
```

### 5. Rolling Deploy

```bash
aws ecs update-service \
  --cluster isli-cluster \
  --service isli-core-api \
  --force-new-deployment
```

### 6. Verify

Create a test agent/task with PII and confirm it can be decrypted correctly:

```bash
curl -sf http://${ALB_DNS}/api/agents | jq '.agents[0].name'
```

## Emergency Key Compromise

If either key is suspected compromised:

1. Rotate immediately using steps above.
2. Audit logs for unauthorized access (CloudTrail, application audit logs).
3. Force logout all sessions (if JWT secret was compromised, all existing tokens become invalid after rotation).
