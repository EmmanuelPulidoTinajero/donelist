# To-do list API — Terraform, RDS, and CI/CD

Tracked implementation for the user's requested activity. Read through `## Log` before acting.

## Specs

- S1: "Crea un repositorio público de GitHub llamado to-do-list-api y sube tu código ahí."
- S2: "Escribe un main.tf que cree la instancia EC2" and deployment must use Terraform `user_data` to clone the repo, install dependencies, and start the app at boot.
- S3: "Cambia tu app para que las tareas se escriban en una base de datos RDS en lugar de en memoria." GET `/tasks` and POST `/tasks` must persist in PostgreSQL.
- S4: "¿Qué servicio usarían para que la app no tenga las credenciales de RDS hardcodeadas?" The implementation must use AWS Secrets Manager and must not hardcode database credentials.
- S5: The learned lab has one existing role and must not create additional IAM roles. Terraform must consume an existing instance profile/role as input rather than creating a role.
- S6: "Workflow de GitHub Actions que provisione la infraestructura con Terraform (trigger manual)."
- S7: "Workflow de destroy." 
- S8: "Pruebas unitarias que corran en CI al crear un PR."
- S9: "Continuous Delivery: al empujar una etiqueta v#.#.#, se crea un release."
- S10: "Continuous Deployment: al llegar un release, se descarga en la EC2 y se reinicia el servidor."
- S11: "Endpoint GET /version."
- S12: "Agrega un endpoint GET /health" that checks the database with a simple query, returns application version, and returns a server timestamp.
- S13: Add a scheduled GitHub Actions workflow every five minutes that requests `/health` and fails unless the response is HTTP 200.
- S14: "No incluyas en el commit el archivo terraform.tfstate" and infrastructure must be destroyable with Terraform.

## Tasks

- T1 [S1-S3,S11-S12] Build the Node.js/Express API with PostgreSQL persistence and tests. Commit: pending.
- T2 [S2,S4-S5,S14] Build parameterized Terraform EC2/RDS/network/secrets configuration without creating IAM roles. Commit: pending.
- T3 [S6-S10,S13] Add CI/CD, release, deployment, and health-monitoring workflows. Commit: pending.
- T4 [S1-S14] Validate locally; validate Terraform statically; validate AWS only after credentials are refreshed. Commit: pending.

## Log

- L1: User requested implementation and testing of the activity described in the conversation, stated that Node.js + Express + PostgreSQL and the current repository/public-repository direction are acceptable, and asked the assistant to use AWS CLI to identify the active account.
- L2: AWS CLI configuration reports region `us-east-1`, but `aws sts get-caller-identity` fails with `InvalidClientTokenId`; credentials must be refreshed before cloud provisioning can be tested.
