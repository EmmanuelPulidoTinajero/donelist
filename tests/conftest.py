"""Shared fixtures: a fake database so the suite never needs PostgreSQL."""

from __future__ import annotations

import pytest


class FakeDatabase:
    """Stand-in for ``src.database.Database`` with per-operation failures."""

    def __init__(self, *, tasks=None, created=None, list_error=None, create_error=None, check_error=None):
        self.tasks = [] if tasks is None else tasks
        self.created = created
        self.list_error = list_error
        self.create_error = create_error
        self.check_error = check_error
        self.calls: list[str] = []
        self.titles: list[str] = []

    def list_tasks(self):
        self.calls.append("list_tasks")
        if self.list_error:
            raise self.list_error
        return self.tasks

    def create_task(self, title):
        self.calls.append("create_task")
        self.titles.append(title)
        if self.create_error:
            raise self.create_error
        return self.created

    def check(self):
        self.calls.append("check")
        if self.check_error:
            raise self.check_error
        return None


@pytest.fixture
def fake_database():
    return FakeDatabase()
