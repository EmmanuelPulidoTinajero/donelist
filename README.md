# to-do-list-api

A small Node.js/Express to-do API backed by PostgreSQL. The Terraform configuration provisions an EC2 application server, a private PostgreSQL RDS instance, a Secrets Manager secret, and security groups.

## API

```bash
npm ci
npm test
DB_HOST=localhost DB_NAME=tasks DB_USER=tasks_app DB_PASSWORD=secret npm start
```

The application exposes:

- `GET /tasks` — returns tasks ordered by ID.
- `POST /tasks` — accepts `{ "title": "..." }` and stores a task.
- `GET /version` — returns the configured `APP_VERSION`.
- `GET /health` — runs `SELECT 1`; returns HTTP 200 and `status: "OK"` when the database is available, otherwise HTTP 503 and `status: "FAIL"`.

Initialize a database with [`db/schema.sql`](db/schema.sql).

## Terraform

Terraform files are under [`infra/`](infra). This configuration deliberately creates **no IAM role** because the learned lab permits only one existing role. Supply an existing EC2 instance profile through `instance_profile_name`; that role must be trusted by EC2 and permit `secretsmanager:GetSecretValue` for the generated database secret. If the existing lab role is not EC2-assumable, the lab must provide an existing instance profile; Terraform cannot safely convert an arbitrary role without creating or changing IAM resources.

The configuration uses the default VPC and its subnets, creates a private RDS PostgreSQL instance, permits PostgreSQL only from the EC2 security group, and stores database credentials in Secrets Manager. The EC2 bootstrap retrieves the secret through its instance profile, initializes `db/schema.sql`, and runs the API as a systemd service. It never stores a database password in Git.

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with the lab region, AMI, key pair, repository URL, and existing instance profile.
terraform init -backend-config="bucket=YOUR_PREEXISTING_STATE_BUCKET" -backend-config="key=to-do-list-api/terraform.tfstate" -backend-config="region=us-east-1"
terraform fmt -recursive
terraform validate
terraform plan
terraform apply
terraform output api_url
# After validation:
terraform destroy
```

The S3 backend bucket must already exist and be permitted by the lab role; Terraform does not create it. Do not commit `terraform.tfstate`, `.terraform/`, or `terraform.tfvars`. The root and `infra/.gitignore` files exclude them.

## GitHub Actions

- `test.yml`: runs unit tests for every pull request.
- `terraform-apply.yml`: manual provisioning workflow using the `infrastructure` environment.
- `terraform-destroy.yml`: manual cleanup workflow.
- `release.yml`: creates a GitHub release for tags matching `v*.*.*`.
- `deploy.yml`: on a published release, SSHs to EC2, checks out the release tag, installs dependencies, and restarts the systemd service.
- `health-monitor.yml`: checks `${API_URL}/health` every five minutes and fails unless the endpoint returns HTTP 200.

Configure these repository/environment values before using workflows:

- Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`, `EC2_SSH_PRIVATE_KEY`, and `EC2_HOST`.
- Variables: `AWS_REGION`, `API_URL`, `TF_STATE_BUCKET`, `AMI_ID`, `INSTANCE_PROFILE_NAME`, and `SSH_KEY_NAME`.
- `terraform-apply.yml` and `terraform-destroy.yml` generate a temporary variables file and use the shared S3 backend; the state is never committed. The backend bucket must be provisioned separately because the learned-lab role may not permit Terraform to create it.
