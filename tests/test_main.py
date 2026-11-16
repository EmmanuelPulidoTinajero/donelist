"""Response contracts of the four endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from conftest import FakeDatabase
from main import create_app, iso_timestamp
from metrics import Counters

FIXED_NOW = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
TASK = {"id": 2, "title": "Ship", "completed": False}


def build(database=None, *, counters=None, version="1.0.0", now=None):
    database = database or FakeDatabase()
    counters = Counters() if counters is None else counters
    app = create_app(
        database=database,
        metrics=counters,
        version=version,
        now=now or (lambda: FIXED_NOW),
    )
    return TestClient(app), database, counters


def test_get_tasks_returns_persisted_tasks():
    database = FakeDatabase(tasks=[{"id": 1, "title": "Study", "completed": False}])
    client, _, _ = build(database)

    response = client.get("/tasks")

    assert response.status_code == 200
    assert response.json() == [{"id": 1, "title": "Study", "completed": False}]
    assert database.calls == ["list_tasks"]


def test_post_tasks_persists_the_trimmed_title():
    database = FakeDatabase(created=TASK)
    client, _, _ = build(database)

    response = client.post("/tasks", json={"title": " Ship "})

    assert response.status_code == 201
    assert response.json() == TASK
    assert database.titles == ["Ship"]


def test_post_tasks_rejects_a_blank_title_without_touching_the_database():
    database = FakeDatabase()
    client, _, _ = build(database)

    response = client.post("/tasks", json={"title": "   "})

    assert response.status_code == 400
    assert response.json() == {"error": "title is required"}
    assert database.calls == []


def test_post_tasks_rejects_a_malformed_body():
    database = FakeDatabase()
    client, _, _ = build(database)

    response = client.post(
        "/tasks", content=b"not json", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 400
    assert response.json() == {"error": "title is required"}
    assert database.calls == []


def test_post_tasks_rejects_an_empty_body():
    database = FakeDatabase()
    client, _, _ = build(database)

    response = client.post("/tasks")

    assert response.status_code == 400
    assert response.json() == {"error": "title is required"}
    assert database.calls == []


def test_get_version_returns_the_configured_version():
    client, _, _ = build(version="2.3.4")

    response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {"version": "2.3.4"}


def test_get_health_reports_ok_when_the_database_responds():
    client, _, _ = build(version="1.2.3")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "OK",
        "version": "1.2.3",
        "timestamp": "2025-01-01T00:00:00.000Z",
    }


def test_get_health_reports_fail_when_the_database_is_unavailable():
    database = FakeDatabase(check_error=RuntimeError("offline"))
    client, _, _ = build(database)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "FAIL",
        "version": "1.0.0",
        "timestamp": "2025-01-01T00:00:00.000Z",
    }


def test_get_tasks_returns_500_and_counts_a_read_error():
    database = FakeDatabase(list_error=RuntimeError("offline"))
    client, _, counters = build(database)

    response = client.get("/tasks")

    assert response.status_code == 500
    assert response.json() == {"error": "Unable to load tasks"}
    assert counters.snapshot()["DbReadErrors"] == 1


def test_get_tasks_counts_nothing_when_the_read_succeeds():
    client, _, counters = build()

    assert client.get("/tasks").status_code == 200
    assert counters.snapshot() == {"DbReadErrors": 0, "DbWriteErrors": 0, "TasksCreated": 0}


def test_post_tasks_returns_500_and_counts_a_write_error():
    database = FakeDatabase(create_error=RuntimeError("offline"))
    client, _, counters = build(database)

    response = client.post("/tasks", json={"title": "Ship"})

    assert response.status_code == 500
    assert response.json() == {"error": "Unable to create task"}
    assert counters.snapshot()["DbWriteErrors"] == 1


def test_post_tasks_counts_a_created_task():
    client, _, counters = build(FakeDatabase(created=TASK))

    assert client.post("/tasks", json={"title": "Ship"}).status_code == 201
    assert counters.snapshot()["TasksCreated"] == 1


def test_get_health_counts_a_read_error():
    client, _, counters = build(FakeDatabase(check_error=RuntimeError("offline")))

    assert client.get("/health").status_code == 503
    assert counters.snapshot()["DbReadErrors"] == 1


def test_iso_timestamp_matches_the_published_format():
    moment = datetime(2025, 3, 4, 5, 6, 7, 891000, tzinfo=timezone.utc)

    assert iso_timestamp(moment) == "2025-03-04T05:06:07.891Z"


@pytest.mark.parametrize("path", ["/tasks", "/version", "/health"])
def test_every_read_endpoint_answers_get(path):
    client, _, _ = build(FakeDatabase(tasks=[]))

    assert client.get(path).status_code in {200, 503}
