# to-do-list-api

A small Node.js/Express to-do API backed by PostgreSQL, provisioned end to end with Terraform and operated through GitHub Actions.

Terraform creates the EC2 application server, the private PostgreSQL RDS instance, the Secrets Manager secret that holds the database credentials, the EC2 key pair, the security groups, the SNS topic and the CloudWatch alarms and dashboard. The EC2 bootstrap installs and runs the API without any manual step.

## API

| Route | Behaviour |
| --- | --- |
| `GET /tasks` | Returns tasks ordered by ID. |
| `POST /tasks` | Accepts `{ "title": "..." }` and stores a task. |
| `GET /version` | Returns the deployed `APP_VERSION` as `{ "version": "..." }`. |
| `GET /health` | Runs `SELECT 1`; returns HTTP 200 with `status: "OK"`, the version and a timestamp, or HTTP 503 with `status: "FAIL"` when the database is unreachable. |

`db/schema.sql` creates the table.

### Run locally

```bash
npm ci
DB_HOST=localhost DB_NAME=tasks DB_USER=tasks_app DB_PASSWORD=secret npm start
```

Without `DB_SECRET_ARN` the API reads `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and `DB_SSL` from the environment. On EC2 only `DB_SECRET_ARN` is set: the API fetches the credentials from Secrets Manager at startup, so no password is ever written into the repository, the user data or the systemd unit.

### Tests

```bash
npm test        # node --test
```

Three suites run without a database or AWS access, because every external dependency is injected:

- `test/app.test.js` — routes, validation, health reporting and the metric counters the handlers emit.
- `test/metrics.test.js` — the durable counter file, including the reset that the CloudWatch publisher performs between runs.
- `test/secrets.test.js` — resolution from Secrets Manager, and the environment fallback.

## Infrastructure

Terraform lives in [`infra/`](infra) and requires **Terraform 1.10 or newer**.

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Fill in the lab region, AMI, repository URL, existing instance profile,
# the alert email and the CIDR allowed to reach port 22.
terraform init -backend-config="bucket=YOUR_PREEXISTING_STATE_BUCKET" \
               -backend-config="key=to-do-list-api/terraform.tfstate" \
               -backend-config="region=us-east-1"
terraform fmt -check -recursive
terraform validate
terraform plan
terraform apply
terraform output api_url
```

`terraform destroy` removes everything this configuration created.

The database password comes from `random_password` and is restricted to the character set RDS accepts: `/`, `@`, `"` and space are excluded, because RDS rejects them in `MasterUserPassword` and the apply would fail only once the instance creation starts.

### Remote state

The state lives in S3 and never in the repository. `infra/versions.tf` declares `encrypt = true` and `use_lockfile = true`, so every run encrypts the object and takes an S3-native lock; no DynamoDB table is needed. The bucket must already exist and be permitted by the lab role, because Terraform does not create it. `*.tfstate`, `.terraform/` and `terraform.tfvars` are ignored by both root and `infra/` `.gitignore` files.

### Key pair

Terraform provisions the EC2 key pair: `tls_private_key` generates a 4096-bit RSA key and `aws_key_pair` registers the public half. The private half lives only in the remote state, so read it once and keep it outside the repository:

```bash
terraform output -raw ssh_private_key_pem > ~/donelist-key.pem
chmod 600 ~/donelist-key.pem
```

Losing the remote state loses that key, and the next apply creates a different key pair.

### Variables

| Variable | Purpose |
| --- | --- |
| `repository_url` | Public repository cloned by EC2 user data. |
| `repository_branch` | Branch cloned by user data. Defaults to `main`; set it to the feature branch while that work is not merged yet. |
| `ami_id` | Amazon Linux 2023 AMI for the region. |
| `instance_profile_name` | Existing EC2 instance profile; Terraform creates no IAM role. |
| `ssh_cidr` | CIDR allowed to reach port 22. No default, validated. |
| `alert_email` | Address subscribed to the alarm topic. |
| `instance_role_name` | Optional. When set, Terraform attaches an inline `cloudwatch:PutMetricData` policy to that existing role. |
| `database_connections_threshold` | Connection count that trips the native RDS alarm. Defaults to 20. |
| `app_version`, `app_port`, `db_name`, `db_username`, `db_instance_class`, `instance_type`, `aws_region`, `project_name` | Sizing and naming. |

The configuration deliberately creates no IAM role, because the learned lab allows a single existing role. If that role cannot be assumed by EC2, the lab must provide an instance profile; Terraform cannot safely convert an arbitrary role without creating IAM resources.

## Continuous integration

`.github/workflows/test.yml` runs `npm ci` and `npm test` for every pull request, with least-privilege permissions and superseded runs cancelled. The grading checklist requires a failing run to block merges into `main`; that is a repository setting, so apply it once by hand:

1. Open any pull request so the `Tests` workflow runs at least once (a check name only becomes selectable after its first run).
2. **Settings → Branches → Add branch protection rule** for `main`.
3. Enable **Require status checks to pass before merging** and select `Tests / Unit tests`.
4. Keep the workflow name `Tests` and the job name `Unit tests`: the required check matches both.

## Release and deployment

1. `release.yml` runs on a tag matching `v*.*.*`. It packages the tagged commit with `git archive`, verifies that the archive is readable and contains `package.json`, and attaches the zip to a GitHub release.
2. `deploy.yml` runs when a release is published. It copies [`scripts/deploy-release.sh`](scripts/deploy-release.sh) to the instance over SSH and runs it with the tag and the asset URL. The script downloads the asset, extracts it over `/opt/to-do-list-api`, runs `npm ci --omit=dev`, records the tag as `APP_VERSION` in `/etc/to-do-list-api.env`, restarts the systemd unit and polls `/version` until the instance reports the new tag.

The instance therefore deploys the exact artifact a reviewer can download from the release page, and never builds from git at deploy time. Deployment is not performed with `scp`.

Because the runners' egress addresses change, `ssh_cidr` must allow the GitHub-hosted runner ranges (or `0.0.0.0/0`) for the deploy job to reach port 22.

## Observability

The API keeps three counters in `/var/lib/to-do-list-api/metrics.json`. A systemd timer runs `observability/publish_metrics.py` once a minute; that script claims the file (renames it) and publishes the deltas with boto3 `put_metric_data` to the `ToDoListApi` namespace, so each datapoint covers only the events since the previous publish.

| Metric | Namespace | Source | Alarm |
| --- | --- | --- | --- |
| `DatabaseConnections` | `AWS/RDS` | Native AWS metric | `Maximum > 20` for 3 minutes |
| `DbReadErrors` | `ToDoListApi` | API counter, published with boto3 | `Sum > 3` in 2 minutes |
| `DbWriteErrors` | `ToDoListApi` | API counter, published with boto3 | `Sum > 3` in 2 minutes |
| `TasksCreated` | `ToDoListApi` | Proposed behaviour metric: task intake | `Sum > 50` in 5 minutes |

Every alarm notifies the `${project_name}-alerts` SNS topic, which has an email subscription to `alert_email`. **Confirm the subscription from the inbox before relying on notifications**; SNS keeps it pending until then.

The dashboard `${project_name}-api` shows the three metric widgets and the alarm state. `.github/workflows/health-monitor.yml` polls `$API_URL/health` every five minutes, opens or updates an issue titled `[health-check-alert]` when it fails, and closes that issue after the API recovers.

If `instance_role_name` is left empty, the EC2 role must already allow `cloudwatch:PutMetricData`, otherwise the publisher logs `AccessDenied` and no custom metric appears.

## Demo and evidence

Suggested order for the recording and the report screenshots:

1. Run `terraform apply` and open the state object in S3 to show the remote backend.
2. Show `terraform output api_url`, then `curl $API_URL/version` and `POST`/`GET /tasks`.
3. Open the CloudWatch dashboard with the three metrics populated.
4. Push a commit, open a pull request and show `Tests / Unit tests` blocking the merge.
5. Tag `v1.0.1`, wait for the release, download the zip from the release page, then show the deploy run and `curl $API_URL/version` returning the new tag.
6. Lower an alarm threshold temporarily (or stop the RDS instance for `DbReadErrors`) so the alarm goes to `ALARM` and the email arrives.

## Repository layout

```
src/            Express app, PostgreSQL pool, Secrets Manager resolution, counters
test/           node:test suites
db/             schema.sql
infra/          Terraform: EC2, RDS, secrets, SNS, alarms, dashboard, user data
observability/  boto3 publisher for the CloudWatch counters
scripts/        deploy-release.sh, used by the deploy workflow
.github/        CI, Terraform apply/destroy, release, deploy and health workflows
```

## Repository and environment configuration

- Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`, `EC2_SSH_PRIVATE_KEY`, `EC2_HOST`.
- Variables: `AWS_REGION`, `API_URL`, `TF_STATE_BUCKET`, `AMI_ID`, `INSTANCE_PROFILE_NAME`, `SSH_CIDR`, `ALERT_EMAIL`.
- `terraform-apply.yml` and `terraform-destroy.yml` generate a temporary `terraform.auto.tfvars.json` and share the same S3 backend; the state is never committed.
