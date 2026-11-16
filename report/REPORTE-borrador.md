# Práctica 4 — To-Do List (CI/CD + Observabilidad)

Nombre: José Emmanuel Pulido Tinajero · Materia: Desarrollo en la Nube (AWS) · Fecha: ____

> Borrador de trabajo. Las secciones marcadas **⟵ TU RESPUESTA** son tuyas: están
> los argumentos técnicos y las preguntas guía, pero la redacción y la experiencia
> tienen que ser tuyas, porque es lo que se evalúa de la reflexión.
> Las tres capturas obligatorias están listadas al final del documento.

---

## 1. Descripción del proyecto

`to-do-list-api` es una API de tareas pendientes escrita en Python (FastAPI) que
persiste en PostgreSQL sobre RDS. Expone cuatro endpoints: `GET /tasks`,
`POST /tasks`, `GET /version` y `GET /health`. Toda la infraestructura se crea
con Terraform (EC2, Security Group, Key Pair, RDS, Secrets Manager, SNS, alarmas
y dashboard), el estado vive en un backend remoto de S3, y el camino del cambio
de código a producción está automatizado con GitHub Actions: pruebas en cada
pull request, release al empujar una etiqueta `v#.#.#`, deploy de ese artefacto
en la instancia, y un chequeo de salud cada 5 minutos.

## 2. Diagrama de arquitectura

```
 ┌──────────────┐   push tag v#.#.#   ┌──────────────────────────┐
 │ Desarrollador│────────────────────▶│ GitHub Actions: release  │
 └──────────────┘                     │  zip del repositorio     │
                                      └────────────┬─────────────┘
                                                   │ asset
                                      ┌────────────▼─────────────┐
                                      │ GitHub Actions: deploy   │
                                      │  SSM Run Command (no SSH)│
                                      └────────────┬─────────────┘
                                                   │
   ┌───────────────────────────────────────────────▼──────────────────┐
   │ EC2  ·  user_data: git clone → venv → pip → schema.sql → systemd │
   │   ┌──────────────────────────────┐                               │
   │   │ FastAPI :8000                │                               │
   │   │  /tasks /version /health     │                               │
   │   └───────┬──────────────┬───────┘                               │
   └───────────┼──────────────┼───────────────────────────────────────┘
               │              │ put_metric_data (boto3)
               │              ▼
               │      ┌──────────────┐   alarma   ┌──────┐   ┌───────┐
               │      │  CloudWatch  │───────────▶│ SNS  │──▶│ email │
               │      │  métricas +  │            └──────┘   └───────┘
               │      │  dashboard   │
               │      └──────────────┘
               │ SELECT / INSERT
               ▼
        ┌──────────────┐        ┌──────────────────┐
        │ RDS Postgres │        │ Secrets Manager  │
        │   (tasks)    │◀───────│ credenciales RDS │
        └──────────────┘  lee   └──────────────────┘
                          en runtime

 Terraform ──▶ crea todo lo anterior · estado en S3 (backend remoto)
 GitHub Actions: health-check (cron */5 min) ──GET /health──▶ EC2
```

## 3. Respuesta 1 — Terraform frente a hacerlo a mano o con bash

**⟵ TU RESPUESTA.** Argumentos que tenés disponibles para construirla:

- La infraestructura se describe, no se ejecuta a mano: `terraform plan` te dice
  los 17 recursos **antes** de crearlos, y `terraform apply` es idempotente.
  Correr el mismo `apply` dos veces no duplica nada; volver a correr un script de
  bash normalmente sí.
- Lo que más cuesta sin Terraform en este proyecto: la **relación entre
  recursos**. El Security Group de la base sólo acepta el puerto 5432 *desde el
  Security Group de la app*; el `user_data` de la instancia necesita el ARN del
  secreto, que no existe hasta que se crea el secreto, que necesita la instancia
  de RDS. A mano eso son diez pasos en el orden correcto y copiar valores entre
  ellos; en Terraform son referencias (`aws_secretsmanager_secret.db.arn`) y
  `depends_on`.
- Diferencia concreta entre `scp` y `user_data`: `scp` es imperativo y ocurre
  *después* del arranque, desde tu máquina, así que la instancia queda en un
  estado intermedio no reproducible y depende de que vos estés ahí; `user_data`
  es declarativo y ocurre *en* el arranque, dentro de la instancia, así que la
  máquina se auto-construye y el resultado es el mismo cada vez. `scp` copia
  archivos; `user_data` ejecuta un bootstrap. La desventaja de `user_data`:
  si falla, Terraform **igual reporta éxito**, porque sólo lo envía. Eso fue
  exactamente el bug que se encontró en este proyecto.
- El sandbox se destruye cada 2 horas: reconstruir a mano cada vez son ~15
  minutos y errores de tipeo; reconstruir con Terraform es un comando.

## 4. Respuesta 2 — Pasos manuales eliminados y riesgo que corrías

**⟵ TU RESPUESTA.** Argumentos disponibles:

- Pasos que ya no hacés a mano: crear la instancia, el Security Group y el Key
  Pair; instalar dependencias; copiar el código con `scp`; crear la base y el
  secreto; correr `CREATE TABLE`; reiniciar el servicio; descargar y desplegar
  una versión; chequear si está viva.
- Riesgos concretos de hacerlo a mano: crear el Security Group de la base con
  `0.0.0.0/0` en el 5432 porque es más rápido; dejar el password en el historial
  de bash o en un `git commit`; desplegar una versión distinta de la que se
  probó porque `git pull` trajo otra cosa; olvidarte de reiniciar el servicio y
  creer que el cambio está en producción cuando no está.
- El pipeline ahora: PR → 35 pruebas + `terraform fmt/validate` (y si falla, no
  se mergea) → tag → release con el zip → deploy del artefacto exacto → `/version`
  confirma qué quedó corriendo. Cada uno de esos pasos dejó de depender de que
  alguien se acuerde.

## 5. Respuesta 3 — Una alarma concreta

**⟵ TU RESPUESTA.** Elegí **`to-do-list-api-db-read-errors`** (es la más
demostrable). Argumentos disponibles:

- **Qué la dispara en la vida real:** la base rechaza conexiones o se queda sin
  capacidad. En el laboratorio lo probás parando RDS: `POST` deja de funcionar y
  la métrica `DbReadErrors` sube.
- **Por qué ese umbral:** `Sum > 3` en 2 períodos de 60 s. No es `> 0` porque un
  1 % de errores transitorios es normal y no justifica despertar a nadie; es
  `> 3` sostenido porque tres fallos en un minuto y dos minutos seguidos ya no es
  ruido, es un patrón.
- **Cómo lo diagnosticás en el dashboard:** el widget de `DbReadErrors` sube
  junto con `AWS/RDS DatabaseConnections` — si las conexiones suben y los errores
  también, es saturación del pool; si los errores suben y las conexiones no, es
  red o el security group.
- **Qué acción tomás:** revisar `sudo journalctl -u to-do-list-api` en la
  instancia, confirmar el estado de RDS, y si el problema es de capacidad subir
  la `db_instance_class` (un campo en `variables.tf`).

## 6. Anexos — capturas obligatorias

| # | Captura | Cómo obtenerla |
|---|---|---|
| 1 | Dashboard de CloudWatch | consola → CloudWatch → Dashboards → `to-do-list-api-api` (4 widgets) |
| 2 | Una alarma en estado `ALARM` | parar RDS, generar errores con `curl`, esperar el período, capturar la alarma **y** el correo de SNS |
| 3 | El tfstate en S3 | `aws s3 ls s3://to-do-list-api-tfstate-647018795197/to-do-list-api/` |

Capturas extra que suman: ejecución verde del workflow de tests en un PR; el
release con su zip adjunto; la corrida de `deploy.yml`; `curl` a los cuatro
endpoints; `SELECT * FROM tasks;` en la base.

---

## Nota honesta para el reporte

Este proyecto empezó en Node y se reescribió en Python. En el camino se
encontraron tres defectos que vale la pena mencionar porque son el mejor
argumento de la reflexión 1:

1. El `user_data` abortaba en un comentario mal formado y `terraform apply`
   igual reportaba éxito. La instancia existía y la aplicación no.
2. El password de RDS se generaba con caracteres que RDS rechaza, y el error
   sólo aparecía al crear la base, no en el `plan`.
3. El deploy por SSH obligaba a abrir el puerto 22 a las IPs de los runners de
   GitHub (que cambian en cada corrida) y a copiar una llave privada a mano en
   cada re-apply. Se cambió a SSM Run Command: sin puerto 22 y sin llave.
