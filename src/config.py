"""Runtime configuration read from the environment.

This module never talks to AWS. Keeping it free of network calls is what makes
the whole configuration layer testable without credentials.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_PORT = 8000
DEFAULT_METRICS_NAMESPACE = "ToDoListApi"
DEFAULT_METRICS_FLUSH_SECONDS = 60.0
SERVICE_NAME = "to-do-list-api"


def _float_env(environ: dict[str, str], name: str, default: float) -> float:
    raw = environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Everything the process needs to boot, resolved once."""

    port: int = DEFAULT_PORT
    version: str = "1.0.0"
    aws_region: str | None = None
    db_secret_arn: str | None = None
    db_ssl: bool = True
    metrics_namespace: str = DEFAULT_METRICS_NAMESPACE
    metrics_flush_seconds: float = DEFAULT_METRICS_FLUSH_SECONDS

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        return cls(
            port=int(env.get("PORT") or DEFAULT_PORT),
            version=env.get("APP_VERSION") or "1.0.0",
            aws_region=env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION"),
            db_secret_arn=env.get("DB_SECRET_ARN") or None,
            db_ssl=(env.get("DB_SSL") or "true").strip().lower() != "false",
            metrics_namespace=env.get("METRICS_NAMESPACE") or DEFAULT_METRICS_NAMESPACE,
            metrics_flush_seconds=_float_env(
                env, "METRICS_FLUSH_SECONDS", DEFAULT_METRICS_FLUSH_SECONDS
            ),
        )
