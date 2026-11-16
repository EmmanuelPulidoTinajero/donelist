"""Process entrypoint: wire configuration, database, metrics and the ASGI server."""

from __future__ import annotations

import sys

import uvicorn

from config import Settings
from credentials import resolve_database_config
from database import Database
from main import create_app
from metrics import CloudWatchPublisher, Counters


def main(environ=None) -> int:
    settings = Settings.from_env(environ)
    try:
        database = _open_database(settings, environ)
    except Exception as error:  # noqa: BLE001 - a boot failure must exit visibly
        print(f"to-do-list-api failed to start: {error}", file=sys.stderr, flush=True)
        return 1

    counters = Counters()
    publisher = CloudWatchPublisher(
        counters,
        namespace=settings.metrics_namespace,
        flush_seconds=settings.metrics_flush_seconds,
        region=settings.aws_region,
    )
    app = create_app(database=database, metrics=counters, version=settings.version)

    publisher.start()
    try:
        uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level="info")
    finally:
        publisher.stop()
        # Publish whatever is still pending before the process goes away.
        publisher.flush_once()
        database.close()
    return 0


def _open_database(settings: Settings, environ) -> Database:
    config = resolve_database_config(environ=environ, region=settings.aws_region)
    database = Database(config)
    database.open()
    return database


if __name__ == "__main__":
    raise SystemExit(main())
