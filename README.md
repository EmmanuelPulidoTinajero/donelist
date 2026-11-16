# to-do-list-api

A small task API with the whole path automated: Terraform provisions the
infrastructure, GitHub Actions tests it, publishes releases, deploys them, and
watches the running service.

- **API**: Python 3.12, FastAPI, psycopg 3 against PostgreSQL on RDS.
- **Credentials**: never in the code; read at runtime from AWS Secrets Manager.
- **Infrastructure**: `terraform/`, state in S3 (never in the repository).
- **Delivery**: a `v#.#.#` tag publishes a release with a zip asset; the deploy
  workflow installs that asset on the instance through SSM Run Command.
- **Observability**: three CloudWatch metrics, one alarm each, an SNS email
  topic, and a dashboard. A scheduled workflow polls `/health` every 5 minutes.

## Architecture

```
 developer ──push tag v#.#.#──▶ GitHub Actions: release
                                       │ zip asset
                                       ▼
 GitHub Actions: deploy ──SSM Run Command──▶ EC2 (FastAPI, systemd)
                                       │            │
                                       │            ├──▶ Secrets Manager (DB credentials)
                                       │            ├──▶ RDS PostgreSQL (tasks)
                                       │            └── put_metric_data ──▶ CloudWatch
                                       │                                    │
                                       │                              alarms ──▶ SNS ──▶ email
                                       └── describe-instances (by Name tag) ──▶ EC2

 GitHub Actions: health-check (cron */5) ──GET /health──▶ EC2
 GitHub Actions: terraform apply/destroy ──▶ VPC, SG, key pair, EC2, RDS, SNS, alarms, dashboard
                                              state ──▶ S3 backend
```

Why delivery uses SSM and not SSH: a GitHub-hosted runner has a different
address on every run, so an SSH rule has to be either wrong or open to the
world, and the private key would have to be stored as a repository secret and
re-copied every time Terraform regenerates it. SSM Run Command asks AWS to run
the script on the instance instead. No port 22, no key, and the instance is
found by its `Name` tag rather than by an IP that changes on every apply.

## Endpoints

| Endpoint | Behaviour |
| --- | --- |
| `GET /tasks` | The stored tasks, oldest first |
| `POST /tasks` | Creates a task; `{"title": "..."}`; 201 with the row, 400 when the title is blank |
| `GET /version` | The deployed version, from `APP_VERSION` |
| `GET /health` | Runs `SELECT 1` on RDS; 200 `{"status":"OK","version":...,"timestamp":...}`, 503 with `"status":"FAIL"` when the database is unreachable |

`GET /docs` serves the generated OpenAPI documentation.

```bash
curl -X POST http://<ec2-ip>:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "estudiar para el examen de desarrollo en la nube", "done": false}'

curl http://<ec2-ip>:8000/tasks
curl http://<ec2-ip>:8000/version
curl -i http://<ec2-ip>:8000/health
```

Only `title` is read. The `done` field in the assignment's examples is ignored,
and a new task always starts unfinished.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
```

The suite needs no PostgreSQL and no AWS: the routes take an injected database
and an injected metrics collector, so every test is offline and deterministic.

To run the service itself you need a reachable PostgreSQL. Without
`DB_SECRET_ARN` the process reads `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`; with it, the JSON secret from Secrets Manager wins.

```bash
python src/server.py    # http://127.0.0.1:8000
```

> `psycopg` loads `libpq` natively. Windows Smart App Control blocks that DLL on
> some machines, so the driver import is lazy: `pytest` works anyway, and the
> real connection only happens on Linux (the instance and CI).

## Provision

`infra/versions.tf` declares an S3 backend. The bucket has to exist before
Terraform can initialize, so create it once per AWS account:

```bash
BUCKET=to-do-list-api-tfstate-<account-id>
aws s3 mb "s3://$BUCKET" --region us-east-1
aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

Then:

```bash
cd infra
terraform init -backend-config="bucket=$BUCKET" \
               -backend-config="key=to-do-list-api/terraform.tfstate" \
               -backend-config="region=us-east-1"
terraform plan
terraform apply
terraform output            # api_url, instance_id, alarm_names, dashboard_name
```

`terraform.tfvars.example` lists the inputs. `ami_id` is no longer needed: the
AMI is resolved by an `aws_ami` data source, because a hardcoded id breaks the
moment the lab is reset.

Nothing sensitive is committed: `terraform.tfstate`, `*.tfvars`,
`terraform.auto.tfvars.json` and saved plans are all ignored, and the RDS
password only lives in Secrets Manager and in the state (on S3, encrypted).

### Getting a shell without SSH

```bash
aws ssm start-session --target "$(cd infra && terraform output -raw instance_id)"
sudo journalctl -u to-do-list-api -n 100 --no-pager
sudo tail -100 /var/log/cloud-init-output.log
```

## Destroy

```bash
cd infra && terraform destroy
```

or run the **Terraform destroy** workflow. The Learner Lab wipes the account
every session, so `destroy` is mostly about being a good citizen, not about
avoiding cost.

## CI/CD workflows

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `test.yml` | pull request | `pytest` plus `terraform fmt -check`, `terraform validate` and a shell syntax check. Mark it as a required status check on `main` so a red run blocks the merge. |
| `terraform-apply.yml` | manual | `init`/`fmt`/`validate`/`apply`, then prints `api_url` and `instance_id` |
| `terraform-destroy.yml` | manual | `terraform destroy` |
| `release.yml` | tag `v*.*.*` | zips the repository, verifies the archive contains the app, publishes the GitHub release with the zip attached |
| `deploy.yml` | release published | resolves the instance by tag and runs `scripts/deploy-release.sh` through SSM Run Command: downloads the release asset, reinstalls dependencies, rewrites `APP_VERSION`, restarts the unit, and waits until `/version` reports the new tag |
| `health-monitor.yml` | cron `*/5 * * * *` | `curl --fail` against `/health`; opens a GitHub issue when it fails and closes it on recovery |

### Repository secrets and variables

Secrets (re-created every time the lab starts a new session):

| Secret | Value |
| --- | --- |
| `AWS_ACCESS_KEY_ID` | Learner Lab access key |
| `AWS_SECRET_ACCESS_KEY` | Learner Lab secret key |
| `AWS_SESSION_TOKEN` | Learner Lab session token |

Variables:

| Variable | Value |
| --- | --- |
| `TF_STATE_BUCKET` | the state bucket created above |
| `INSTANCE_PROFILE_NAME` | `LabInstanceProfile` |
| `ALERT_EMAIL` | the address subscribed to the SNS topic |
| `API_URL` | `terraform output -raw api_url`, refreshed after every apply |
| `AWS_REGION` | `us-east-1` (optional, defaults to it) |
| `PROJECT_NAME` | `to-do-list-api` (optional, defaults to it) |

`API_URL` changes with every new instance, and the lab credentials expire with
the session, so those two are the ones to refresh each time.

`scripts/set-github-config.sh` writes all nine values in one command. It reads
the credentials from the AWS CLI profile and pipes them into `gh secret set`,
so no key is ever printed or passed as an argument, and it refuses to write
`TF_STATE_BUCKET` when the bucket does not exist, which would otherwise surface
much later as a confusing `terraform init` failure:

```bash
./scripts/set-github-config.sh http://<instance-ip>:8000   # right after an apply
./scripts/set-github-config.sh                             # credentials only
```

## Observability

Three metrics, three alarms, one SNS topic subscribed by email.

| # | Metric | Kind | Namespace | Alarm |
| --- | --- | --- | --- | --- |
| 1 | `DatabaseConnections` | native AWS | `AWS/RDS` | `Maximum > 20` for 3 × 60 s |
| 2 | `DbReadErrors` / `DbWriteErrors` | instrumented (`put_metric_data`) | `ToDoListApi` | `Sum > 3` for 2 × 60 s |
| 3 | `TasksCreated` | instrumented (`put_metric_data`) | `ToDoListApi` | `Sum > 50` over 300 s |

The counters live in the process and a background thread flushes them with
`put_metric_data` every `METRICS_FLUSH_SECONDS` (60). A failed publish puts the
values back, so a CloudWatch hiccup cannot silently drop the datapoints the
alarms depend on.

Why `TasksCreated`: it is the only metric that describes what the product does.
A burst means either real adoption or a retry loop hammering `POST /tasks`, and
both are worth knowing; the number also gives the report a baseline for normal
traffic.

To prove metric 2 reacts, stop the database and call the API:

```bash
aws rds stop-db-instance --db-instance-identifier to-do-list-api
curl -i http://<ec2-ip>:8000/tasks      # 500, and DbReadErrors increments
curl -i http://<ec2-ip>:8000/health     # 503,
aws cloudwatch get-metric-statistics --namespace ToDoListApi \
  --metric-name DbReadErrors --start-time "$(date -u -d '-15 min' +%FT%TZ)" \
  --end-time "$(date -u +%FT%TZ)" --period 60 --statistics Sum
aws rds start-db-instance --db-instance-identifier to-do-list-api
```

The dashboard is `to-do-list-api-api` in CloudWatch; its JSON lives in
`infra/dashboard.json.tftpl` and is applied by Terraform, not clicked together.

## Evidence set for the report

1. CloudWatch dashboard with the three metrics.
2. An alarm in `ALARM` state (and the email it sent).
3. The tfstate object in S3: `aws s3 ls s3://$BUCKET/to-do-list-api/`.
4. A green `test.yml` run on a pull request.
5. A release with its zip asset, and the `deploy.yml` run that installed it.
6. `curl` output for `/tasks`, `/version` and `/health`, plus
   `SELECT * FROM tasks;` on the database.

## Repository layout

```
src/            FastAPI app: main.py (routes), server.py (wiring), database.py,
                credentials.py (Secrets Manager), metrics.py (boto3), config.py
tests/          pytest suite, offline
db/schema.sql   the only table, applied by user_data
infra/          Terraform: EC2, SG, key pair, RDS, Secrets Manager, SNS,
                alarms, dashboard, user_data template
scripts/        deploy-release.sh, executed on the instance over SSM
odd/tasks/      the working documents behind the implementation
```
