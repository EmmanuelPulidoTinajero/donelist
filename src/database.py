"""PostgreSQL access through psycopg 3 and its connection pool.

``psycopg`` is imported inside the methods on purpose. The test suite injects a
fake database, so running pytest never needs libpq, which Windows Smart App
Control blocks on some machines. The real driver is only loaded when the
process actually connects, on the instance or in CI.
"""

from __future__ import annotations

LIST_TASKS_SQL = "SELECT id, title, completed, created_at FROM tasks ORDER BY id ASC"
CREATE_TASK_SQL = (
    "INSERT INTO tasks (title) VALUES (%(title)s) "
    "RETURNING id, title, completed, created_at"
)
HEALTHCHECK_SQL = "SELECT 1"


def connection_kwargs(config: dict) -> dict:
    """Translate the resolved configuration into psycopg connection keywords."""
    kwargs = {
        "host": config["host"],
        "port": int(config["port"]),
        "dbname": config["database"],
        "user": config["user"],
        "password": config["password"],
    }
    if config.get("ssl"):
        # Encrypt the connection without pinning the RDS CA bundle.
        kwargs["sslmode"] = "require"
    return kwargs


class Database:
    """The three database operations the API exposes, and nothing else."""

    def __init__(self, config: dict, *, min_size: int = 1, max_size: int = 4, timeout: float = 5.0):
        self._kwargs = connection_kwargs(config)
        self._min_size = min_size
        self._max_size = max_size
        self._timeout = timeout
        self._pool = None

    def open(self) -> None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(
            kwargs={**self._kwargs, "row_factory": dict_row},
            min_size=self._min_size,
            max_size=self._max_size,
            timeout=self._timeout,
            open=False,
        )
        self._pool.open(wait=True, timeout=self._timeout)

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    def _require_pool(self):
        if self._pool is None:
            raise RuntimeError("The database pool is not open")
        return self._pool

    def list_tasks(self) -> list[dict]:
        with self._require_pool().connection() as connection:
            return connection.execute(LIST_TASKS_SQL).fetchall()

    def create_task(self, title: str) -> dict:
        with self._require_pool().connection() as connection:
            return connection.execute(CREATE_TASK_SQL, {"title": title}).fetchone()

    def check(self) -> None:
        with self._require_pool().connection() as connection:
            connection.execute(HEALTHCHECK_SQL)
