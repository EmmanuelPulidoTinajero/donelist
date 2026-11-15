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

Terraform also provisions the EC2 key pair: `tls_private_key` generates the RSA key and `aws_key_pair` registers the public half. The private half only lives in the remote state, so read it once and keep it outside the repository:

```bash
cd infra
terraform output -raw ssh_private_key_pem > key.pem
chmod 600 key.pem
```

`ssh_cidr` has no default on purpose. The deploy workflow connects from GitHub-hosted runners, whose addresses change, so allow `0.0.0.0/0` if you rely on that automation, or your own address if you only need manual shell access.

> Losing the remote state loses that private key, and Terraform would create a different key pair on the next apply.

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with the lab region, AMI, repository URL, existing instance profile,
# alert email, and the CIDR allowed to reach port 22. Terraform creates the key pair.
terraform init -backend-config="bucket=YOUR_PREEXISTING_STATE_BUCKET" -backend-config="key=to-do-list-api/terraform.tfstate" -backend-config="region=us-east-1"
terraform fmt -recursive
terraform validate
terraform plan
terraform apply
terraform output api_url
# After validation:
terraform destroy
```

The S3 backend bucket must already exist and be permitted by the lab role; Terraform does not create it. Encryption and state locking are declared in `infra/versions.tf` (`encrypt = true`, `use_lockfile = true`), so every run locks the state through S3 itself and requires Terraform 1.10 or newer. Do not commit `terraform.tfstate`, `.terraform/`, or `terraform.tfvars`. The root and `infra/.gitignore` files exclude them.

## GitHub Actions

- `test.yml`: runs the unit test suite for every pull request.
- `terraform-apply.yml`: manual provisioning workflow using the `infrastructure` environment.
- `terraform-destroy.yml`: manual cleanup workflow.
- `release.yml`: for tags matching `v*.*.*`, packages the repository with `git archive` and attaches the zip to a GitHub release.
- `deploy.yml`: on a published release, copies [`scripts/deploy-release.sh`](scripts/deploy-release.sh) to EC2, which downloads the release asset, installs it, records the tag as `APP_VERSION` and restarts the systemd service until `/version` reports the new version.
- `health-monitor.yml`: checks `${API_URL}/health` every five minutes, opens or updates an issue titled `[health-check-alert]` when it fails, and closes that issue after a passing run.

Configure these repository/environment values before using workflows:

- Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`, `EC2_SSH_PRIVATE_KEY`, and `EC2_HOST`.
- Variables: `AWS_REGION`, `API_URL`, `TF_STATE_BUCKET`, `AMI_ID`, `INSTANCE_PROFILE_NAME`, `SSH_CIDR`, and `ALERT_EMAIL`.
- `terraform-apply.yml` and `terraform-destroy.yml` generate a temporary variables file and use the shared S3 backend; the state is never committed. The backend bucket must be provisioned separately because the learned-lab role may not permit Terraform to create it.

### Required status check

The grading checklist requires a failing CI run to block merges into `main`. That is a repository setting, so it has to be applied once by hand:

1. Open any pull request so the `Tests` workflow runs at least once; a check name only becomes selectable after its first run.
2. Go to **Settings → Branches → Add branch protection rule** (or edit the existing rule for `main`).
3. Enable **Require status checks to pass before merging** and select `Tests / Unit tests`.
4. Leave the workflow name `Tests` and the job name `Unit tests` untouched: the required check matches on both.

The job runs `npm test`, which executes the suites in `test/app.test.js`, `test/metrics.test.js` and `test/secrets.test.js`; it uses `npm ci`, so `package-lock.json` must stay committed.
