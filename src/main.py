"""The to-do-list API.

Every response contract here is the one the project already froze:
``GET /tasks`` returns the list, ``POST /tasks`` returns the created row with
201, ``GET /version`` returns the deployed version, and ``GET /health`` returns
OK/FAIL with the version and a server timestamp, using HTTP 503 on failure so
that ``curl --fail`` in the health workflow reacts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

DEFAULT_VERSION = "1.0.0"


def iso_timestamp(moment: datetime) -> str:
    """Render a UTC timestamp the way the project already published it."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


def _metrics(metrics):
    """Tolerate a missing collector so the app can run without instrumentation."""
    if metrics is None:
        raise ValueError("A metrics collector is required")
    return metrics


def create_app(*, database, metrics, version: str = DEFAULT_VERSION, now=None) -> FastAPI:
    """Build the application around an injected database and metrics collector.

    Both are injected because the API owns no connection logic: that keeps the
    routes testable without PostgreSQL and without AWS.
    """
    clock = now or (lambda: datetime.now(timezone.utc))
    counters = _metrics(metrics)

    app = FastAPI(title="to-do-list-api", version=version, docs_url="/docs", redoc_url=None)

    @app.get("/tasks")
    def list_tasks():
        try:
            return jsonable_encoder(database.list_tasks())
        except Exception:  # noqa: BLE001 - any database failure is a 500 for this route
            counters.increment("DbReadErrors")
            return _error(500, "Unable to load tasks")

    @app.post("/tasks", status_code=201)
    async def create_task(request: Request):
        title = await _read_title(request)
        if not title:
            return _error(400, "title is required")

        try:
            row = database.create_task(title)
        except Exception:  # noqa: BLE001 - any database failure is a 500 for this route
            counters.increment("DbWriteErrors")
            return _error(500, "Unable to create task")

        counters.increment("TasksCreated")
        return jsonable_encoder(row)

    @app.get("/version")
    def get_version():
        return {"version": version}

    @app.get("/health")
    def health():
        timestamp = iso_timestamp(clock())
        try:
            database.check()
        except Exception:  # noqa: BLE001 - the whole point of this route is to report it
            counters.increment("DbReadErrors")
            return JSONResponse(
                status_code=503,
                content={"status": "FAIL", "version": version, "timestamp": timestamp},
            )
        return {"status": "OK", "version": version, "timestamp": timestamp}

    return app


async def _read_title(request: Request) -> str:
    """Return the trimmed title, or an empty string when the body is unusable.

    The body is read here instead of through a Pydantic model on purpose: a
    missing or malformed body has to answer 400 with ``title is required``,
    which is the contract the project already published, not a 422.
    """
    try:
        raw = await request.body()
    except Exception:  # noqa: BLE001 - an unreadable body is simply not a title
        return ""
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    title = payload.get("title")
    if not isinstance(title, str):
        return ""
    return title.strip()
