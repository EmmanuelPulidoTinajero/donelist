# Práctica 4 — To-Do List (CI/CD + Observabilidad)

Tracked closure of Práctica 4 grading checklist. Read through `## Log` before acting.

## Specs

- S1: "Entregables completos: reporte con descripción, diagrama de arquitectura, anexos y respuestas, y repositorio."
- S2: "Infraestructura provisionada completamente con Terraform (EC2, Security Group, Key Pair y RDS). El tfstate vive en un backend remoto y no está en el repositorio. Sin captura de pantalla de S3 o HCP se pierden los puntos."
- S3: "Credenciales de RDS en Secrets Manager, leídas por la app en tiempo de ejecución, no hardcodeadas."
- S4: "Workflows de GitHub Actions para provisionar y destruir la infraestructura, con trigger manual, corren exitosamente."
- S5: "Aplicación to-do-list completa: GET /tasks y POST /tasks funcionan y persisten en RDS. GET /version regresa la versión desplegada y GET /health verifica la conexión a la base de datos, la versión y un timestamp."
- S6: "Al menos 3 pruebas unitarias corren en el workflow de CI al abrir un PR, y bloquean el merge a main si fallan."
- S7: "Flujo de Continuous Delivery: una etiqueta v#.#.# crea un release en GitHub. Flujo de Continuous Deployment: un release nuevo se descarga y despliega en la EC2."
- S8: "Instrumentación de las 3 métricas (1 nativa de AWS, 2 propias vía boto3, incluyendo la de errores de RDS) y una alarma de CloudWatch configurada para cada una, notificando por correo a través de un tópico de SNS. Sin captura de pantalla de la alarma se pierden los puntos."
- S9: "Dashboard que visualiza las 3 métricas, y workflow que monitorea /health cada 5 minutos. Sin captura de pantalla del dashboard se pierden los puntos."
- S10: "La instancia EC2 arranca con user_data que clona el repositorio, instala dependencias y levanta la aplicación sin intervención manual (sin SSH ni scp)."
- S11: "un workflow de Continuous Delivery crea un release en GitHub con el repositorio comprimido en zip."
- S12: "Una métrica instrumentada por ti con put_metric_data (boto3) que reporte la cantidad de errores al leer o escribir en RDS" plus "Una métrica más, también instrumentada por ti, que tú propongas sobre el comportamiento de tu to-do-list."
- S13: Report "Máximo 2 hojas. Sin portada." with the three reflection answers and the three mandatory screenshots (dashboard, alarm triggering, tfstate in S3/HCP).

## Tasks

- T1 [S3,S8,S12] App reads the RDS secret from Secrets Manager at runtime; custom CloudWatch metrics published (RDS read/write errors + proposed behavior metric); Terraform SNS topic, email subscription and the two custom alarms; native AWS metric identified and alarmed. Commit: pending.
- T2 [S9] CloudWatch dashboard definition plus Terraform dashboard resource; health-monitor keeps the 5-minute schedule and gains a notification path. Commit: pending.
- T3 [S7,S11] Release workflow packages the repository as a zip asset; deploy workflow downloads that asset, refreshes `APP_VERSION` and restarts the service so `/version` advances. Commit: pending.
- T4 [S6] Committed `package-lock.json` so `npm ci` works, plus README instructions for the required status check on `main`. Commit: pending.
- T5 [S2] `aws_key_pair` managed by Terraform; remote backend with encryption and state locking documented; SSH ingress narrowed. Commit: pending.
- T6 [S4,S5,S10] Preserve provision/destroy/CI/user_data behavior while the above land; no SSH or scp step introduced. Commit: pending.
- T7 [S1,S13] README rewrite (run, provision, destroy, observability, evidence/screenshots, demo steps) and report draft with the three reflection answers and the architecture diagram. Commit: pending.

## Log

- L1: User request, verbatim (module delivered text): "olbida eso primero checa los warnings que me dio la terminal y ayuudame a coirregirlos luego quiero que cheques y hagas una exploración del proyecto para checar que se cumpla con lo siguiente Práctica 4: To-Do List (CI/CD + Observabilidad) ... 1 Descripción de la actividad • Entrega Individual ... to-do-list-api es un API para gestionar tareas pendientes, con las tareas persistidas en una base de datos RDS ... GET /tasks / POST /tasks / GET /version / GET /health ... main.tf, variables.tf y outputs.tf que creen la instancia EC2 con su Security Group y Key Pair ... user_data ... RDS ... Secrets Manager ... backend remoto (S3 o HCP) ... nunca lo subas al repositorio ... al menos 3 pruebas unitarias ... CI al abrir un Pull Request ... etiqueta v#.#.# crea un release en GitHub con el repositorio comprimido en zip ... Deploy: al publicarse un release nuevo ... descarga ese artefacto en la instancia EC2 y reinicia el servidor ... Métricas: al menos 3 (nativa de AWS / put_metric_data (boto3) de errores RDS / una propuesta) ... Alarmas: una por cada métrica ... SNS ... correo ... Dashboard ... workflow provision.yml, destroy.yml, ci.yml, release.yml, deploy.yml, health-check.yml ... Reporte en PDF máximo 2 hojas ... checklist de revisión ... el problema creo que está relacionado al nivel de esfuerso o de pensamiento que tienes como modelo aquí en gentle-shell por que creo que está en automático igual tu puedes checarlo". Full text of the seven checklist items is quoted verbatim in S1-S13 of this document.
- L2: Warned CRLF line endings explained and silenced with a new `.gitattributes` (`* text=auto eol=lf`); `core.autocrlf` left untouched. Reasoning level confirmed as `medium`, not automatic; user advised `/thinking` + `Ctrl+S`.
- L3: Read-only audit of the repository against the seven checklist items mapped as S1-S13; gaps recorded in T1-T7. Audit evidence: `src/app.js:13-52` endpoints OK, `infra/main.tf:110-130` EC2, `infra/versions.tf:4` `backend "s3" {}` without encrypt/locking, `infra/main.tf:115` `key_name = var.ssh_key_name` with no `aws_key_pair`, `infra/user_data.sh.tftpl:19` secret read by AWS CLI at boot, `test/app.test.js` 6 tests with `.github/workflows/test.yml:13` `npm ci` and no lockfile, `.github/workflows/release.yml:16` release without `files:`, `.github/workflows/deploy.yml:25` SSH `git checkout` instead of a release asset, no CloudWatch/SNS/alarm/dashboard artifacts anywhere.
- L4: User decision on ordering: "Todo en orden del checklist" — 8 → 7 → 6 → 2 → 3 → README, one verifiable commit per block.
