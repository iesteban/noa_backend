# Add Secret

Add a new secret/environment variable to the Noa backend. This wires it through all 8 required locations so it's available in local dev, staging, and production.

The user must provide:
- **Secret name** — in UPPER_SNAKE_CASE (e.g. `MY_NEW_SECRET`)
- **Staging value**
- **Production value**
- **Description** — one line describing what it's for

If any of these are missing, ask before proceeding.

## Steps — execute in order

### 1. `app/config.py`
Add a field to the `Settings` class. Use `str = ""` as the default (or a sensible typed default if appropriate):
```python
my_new_secret: str = ""
```
The field name is the secret name lowercased.

### 2. `.env.staging`
Append to the file:
```
MY_NEW_SECRET=<staging-value>
```

### 3. `.env.production`
Append to the file:
```
MY_NEW_SECRET=<production-value>
```

### 4. `infra/terraform/variables.tf`
Add a variable block before the closing of the file:
```hcl
variable "my_new_secret" {
  description = "<description>"
  type        = string
  sensitive   = true
  default     = ""
}
```
The variable name is the secret name lowercased.

### 5. `infra/terraform/containers.tf`
Inside the `env` block of `scaleway_container.api`, add a line aligned with the existing entries:
```hcl
MY_NEW_SECRET = var.my_new_secret
```

### 6. `.github/workflows/ci.yml`
Inside the `env:` block of the **Deploy (update container image)** step, add:
```yaml
TF_VAR_my_new_secret: ${{ secrets.STAGING_MY_NEW_SECRET }}
```

### 7. `.github/workflows/deploy-production.yml`
Inside the `env:` block of the **Deploy (update container image)** step, add:
```yaml
TF_VAR_my_new_secret: ${{ secrets.PRODUCTION_MY_NEW_SECRET }}
```

### 8. GitHub secrets
Run both commands:
```bash
gh secret set STAGING_MY_NEW_SECRET --body "<staging-value>" -R iesteban/noa_backend
gh secret set PRODUCTION_MY_NEW_SECRET --body "<production-value>" -R iesteban/noa_backend
```

## When done
Confirm all 8 steps completed and remind the user that the new env var will be live on the next deploy to main.
