# To-do list API — Python rewrite (FastAPI, SSM deploy, in-process metrics)

Supersedes the Node.js implementation in `src/` while keeping every contract that
`odd/tasks/todo-list-terraform-rds.md` and `odd/tasks/practica4-ci-cd-observabilidad.md`
already froze. Read through `## Log` before acting.

## Specs

- S1: "lo conviertas a python ya que ese si lo tengo instalado para que puedas hacer en todo caso las validaciones locales del proyecto". The API must run on Python so the author can execute the test suite locally.
- S2: "lo único que quiero que me consultes son las preguntas de las desiciones téncicas que en la actividad yo tengo que tomar para aprender del tema eso es importante que me lo preguntes y que a de más me lo expliques".
- S3: Recorded decisions (L2): FastAPI + Uvicorn; deploy through SSM Run Command; custom metrics published in-process with boto3; psycopg 3 with `psycopg_pool`.
- S4: Every endpoint contract from `practica4-ci-cd-observabilidad.md` S5 survives unchanged: `GET /tasks` 200 with the task list; `POST /tasks` 201 with the created row, 400 `{"error":"title is required"}` for a blank title without touching the database, 500 on a database failure; `GET /version` 200 `{"version": <APP_VERSION>}`; `GET /health` 200 `{"status":"OK","version":...,"timestamp":...}` or 503 with `"status":"FAIL"`.
- S5: The counters `DbReadErrors`, `DbWriteErrors` and `TasksCreated` keep their meaning: increments happen on exactly the events the Node tests pinned (`test/app.test.js`).
- S6: `GET /health` keeps returning HTTP 503 on a database failure, because `.github/workflows/health-monitor.yml` relies on `curl --fail`.
- S7: The API listens on port 8000 by default, matching the activity's `curl http://<ip-de-ec2>:8000/tasks` examples.
- S8: `user_data` must boot the API with no SSH and no scp; it must not abort on a non-fatal command, and the shell file must be syntactically valid (`bash -n`).
- S9: The deploy path must reach the instance without port 22 and without a private key in a repository secret; a published release stays the deployed artifact.
- S10: `terraform fmt -check -recursive` and `terraform validate` stay clean; no IAM role is created (Learner Lab constraint from the superseded document's S5).
- S11: Local validation is `pytest` green, `bash -n` on every shell file, `terraform fmt -check -recursive`, and `terraform validate`.

## Tasks

- T1 [S1,S3,S4,S5,S7] Python application: config, Secrets Manager resolution, psycopg pool, FastAPI routes, boto3 metric publisher, `requirements.txt`. Commit: `1091479`.
- T2 [S4,S5,S11] Pytest suite covering every behaviour the Node suite pinned, plus the publisher. Commit: `1091479`.
- T3 [S8,S9,S10] Terraform: fix the broken `user_data` comment, install the Python runtime, look the AMI up with a data source, default the app port to 8000, and stop depending on the SSH key for delivery. Commit: `81cb99c`.
- T4 [S9] Workflows: pytest in CI, release asset check for the Python layout, SSM-based deploy, unchanged provision/destroy/health-monitor. Commit: `8c32ffa`.
- T5 [S11] Local validation: `pytest`, `bash -n`, `terraform fmt -check -recursive`, `terraform validate`, `terraform plan` against the restored remote backend. Commit: `8c32ffa` carries the validated files; the plan itself is not committed.
- T6 [S8,S9] Real deployment through Terraform and SSM and the evidence set the rubric requires (endpoints, `SELECT * FROM tasks`, metrics, alarms, dashboard, tfstate). Commit: pending.
- T7 [S9] Tag `v1.1.0`, publish the release, deploy it through SSM and confirm `/version` advanced. Commit: pending.
- T8 [S2] README rewrite for the Python layout plus the two-page report with the architecture diagram and the three reflection answers. Commit: README landed in `8c32ffa`; report pending.
- T9 [S1] Remove the Node implementation, `observability/publish_metrics.py`, its tests and `package.json`. Commit: `1091479`.

## Delivery slices

Branch `feature/todo-list-terraform-rds`.

- Slice 6 — closed: the Python API, its test suite and the Node removal, `1091479`. 1057 insertions and 2415 deletions: the whole application plus the suite, because splitting the app from the tests would leave an intermediate commit that cannot be run.
- Slice 7 — closed: the repaired bootstrap and the Python runtime in `81cb99c`.
- Slice 8 — closed: SSM delivery, CI hardening and the README in `8c32ffa`. The slice boundary for the next change is `8c32ffa`.
- History note: an earlier attempt created `aa2ee34`, `718c4d1` and `0ed1edc` from a `git add` that a safety guard blocked, so `aa2ee34` contained only the Node deletions. The three commits were rebuilt from `27274df` before anything was pushed, and the slice commits above are the ones that count.

## Log

- L1: User request, verbatim: "quiero que recuperes lo que estábamos haciendo en su momento sentí que no estábamos abansando y por lo tanto primero quiero una revición profunda te pasaré todas las instrucciones de la actividad para que evalúes el estado actual del proyecto y en su caso te pido que lo conviertas a python ya que ese si lo tengo instalado para que puedas hacer en todo caso las validaciones locales del proyecto lo único que quiero que me consultes son las preguntas de las desiciones téncicas que en la actividad yo tengo que tomar para aprender del tema eso es importante que me lo preguntes y que a de más me lo expliques para que yo pueda tener el entendimiento suficiente de la actividad y de los conseptos importantes así como de los flujos del producto quiero que esta revición profunda se enfoque en entender lo que se estába haciendo para poder corregir o de plano cambiar lo que se considere incorrecto ya se tienen credenciales de awscli listas para el despliegue y las pruevas de la infrestructura".
- L2: Review findings that drive this slice. Verified live: AWS credentials valid again (account 647018795197, role `voclabs`); no EC2, no RDS and no S3 buckets existed, so the `to-do-list-api-tfstate-647018795197` backend was gone and was recreated with versioning, AES256 and public-access block; `cloudwatch:PutMetricData` succeeds with the lab role; `LabRole` carries `AmazonSSMManagedInstanceCore`, which makes SSM Run Command available; default VPC `vpc-0d444a684030d7067` exists; `terraform fmt -check -recursive` passes; `node`/`npm` are absent and Python 3.14.7 is present. Critical defect confirmed by reading: `infra/user_data.sh.tftpl:9-10` lost the `#` on the second comment line, so `set -euo pipefail` aborted the bootstrap on a nonexistent command and no instance ever ran the app. Design defects accepted for change: SSH-based delivery with a Terraform-generated key re-copied into a repository secret, and a three-mechanism metrics file plus systemd timer that existed only because Node could not call boto3. Decisions taken with the author in this session: FastAPI + Uvicorn, SSM Run Command, in-process boto3 publishing, psycopg 3 with a pool.
- L3: Toolchain findings while implementing. `psycopg[binary]` installs but cannot load `libpq` on this machine because Windows Smart App Control blocks the DLL, so `database.py` imports the driver lazily and the suite never needs it. A local module named `secrets.py` shadowed the standard library and broke FastAPI's own imports during collection; it was renamed to `credentials.py`. `terraform validate` initially failed on `user_data.sh.tftpl` because a comment contained an unescaped `${name}` that Terraform tried to resolve; both that comment and the file header now document the `$${NAME}` escape rule.
- L4: Local validation evidence for T5. `pytest` 35 passed; `bash -n` clean on `infra/user_data.sh.tftpl` and `scripts/deploy-release.sh`; `terraform fmt -check -recursive` clean; `terraform validate` clean; `terraform plan` against the restored S3 backend reported `17 to add, 0 to change, 0 to destroy` and the `aws_ami` data source resolved `ami-0b71756f4d851f798`, the same image the hardcoded variable carried.
- L5: Delivery is gated by receipt-driven development and the gate found three provider limits in sequence. (a) `lens_context_budget_exceeded` for the whole `27274df..HEAD` candidate: the provider refuses to truncate reviewer evidence, so the change has to be reviewed as the slice commits one at a time. (b) A `git push` was refused until the pending candidate carries a native review outcome. (c) `reviewer-empty-output` on slice 8: `nan/glm5.3-flash` spent its entire 16384-token output budget on reasoning and emitted no verdict for `review-resilience`. The project-local routing store `.pi/gentle-ai/models.json` was changed from `thinking: high` to `thinking: medium` for the four review lenses; the global store stays human-owned and untouched. Next step: re-run the slice review, then push and deploy.
