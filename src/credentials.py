"""Database credentials resolved at runtime.

The deployment never ships a password. ``DB_SECRET_ARN`` points at the
Secrets Manager secret Terraform created, and the process reads it on boot.
The ``DB_*`` variables stay as a fallback so the same code runs locally
without AWS.
"""

from __future__ import annotations

import json
import os

DEFAULT_DB_PORT = 5432
DEFAULT_DB_NAME = "tasks"
DEFAULT_DB_USER = "tasks"


def config_from_environment(environ: dict[str, str] | None = None) -> dict:
    """Connection settings published directly through the environment."""
    env = os.environ if environ is None else environ
    return {
        "host": env.get("DB_HOST"),
        "port": int(env.get("DB_PORT") or DEFAULT_DB_PORT),
        "database": env.get("DB_NAME") or DEFAULT_DB_NAME,
        "user": env.get("DB_USER") or DEFAULT_DB_USER,
        "password": env.get("DB_PASSWORD"),
        "ssl": (env.get("DB_SSL") or "false").strip().lower() == "true",
    }


def secret_entry_to_config(secret: dict, ssl_enabled: bool = True) -> dict:
    """Translate the JSON stored in Secrets Manager into connection settings."""
    if not isinstance(secret, dict):
        raise ValueError("The database secret is not a JSON object")
    return {
        "host": secret["host"],
        "port": int(secret.get("port") or DEFAULT_DB_PORT),
        "database": secret["database"],
        "user": secret["username"],
        "password": secret["password"],
        "ssl": ssl_enabled,
    }


def default_secret_client(region: str | None):
    """A real Secrets Manager client. Imported lazily so tests stay offline."""
    import boto3

    return boto3.client("secretsmanager", region_name=region)


def resolve_database_config(
    *,
    environ: dict[str, str] | None = None,
    region: str | None = None,
    create_secret_client=default_secret_client,
) -> dict:
    """Prefer Secrets Manager; fall back to DB_* variables when no ARN is set."""
    env = os.environ if environ is None else environ
    secret_arn = env.get("DB_SECRET_ARN")
    if not secret_arn:
        return config_from_environment(env)

    client = create_secret_client(region or env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION"))
    try:
        response = client.get_secret_value(SecretId=secret_arn)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    payload = response.get("SecretString")
    if not isinstance(payload, str):
        raise ValueError("Secrets Manager returned no SecretString")
    ssl_enabled = (env.get("DB_SSL") or "true").strip().lower() != "false"
    return secret_entry_to_config(json.loads(payload), ssl_enabled=ssl_enabled)
