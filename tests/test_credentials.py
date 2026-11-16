"""Credentials resolved at runtime from Secrets Manager, never hardcoded."""

from __future__ import annotations

import json

import pytest

from credentials import config_from_environment, resolve_database_config, secret_entry_to_config

SECRET_ARN = "arn:aws:secretsmanager:us-east-1:000000000000:secret:to-do-list-api/database"
SECRET_PAYLOAD = {
    "host": "db.example.internal",
    "port": 5432,
    "database": "tasks",
    "username": "tasks_app",
    "password": "p@ss-from-secret",
}


class FakeSecretClient:
    def __init__(self, payload=None):
        self.requested: list[str] = []
        self.closed = False
        self.payload = json.dumps(SECRET_PAYLOAD if payload is None else payload)

    def get_secret_value(self, *, SecretId):
        self.requested.append(SecretId)
        return {"SecretString": self.payload}

    def close(self):
        self.closed = True


def test_the_secret_is_read_at_runtime_and_wins_over_environment_values():
    client = FakeSecretClient()

    config = resolve_database_config(
        environ={"DB_SECRET_ARN": SECRET_ARN, "DB_PASSWORD": "stale-environment-password"},
        create_secret_client=lambda region: client,
    )

    assert client.requested == [SECRET_ARN]
    assert client.closed is True
    assert config == {
        "host": "db.example.internal",
        "port": 5432,
        "database": "tasks",
        "user": "tasks_app",
        "password": "p@ss-from-secret",
        "ssl": True,
    }


def test_without_a_secret_arn_the_environment_variables_are_used():
    def must_not_be_called(region):
        raise AssertionError("Secrets Manager must not be called without DB_SECRET_ARN")

    config = resolve_database_config(
        environ={"DB_HOST": "localhost", "DB_USER": "tasks", "DB_PASSWORD": "local"},
        create_secret_client=must_not_be_called,
    )

    assert config == {
        "host": "localhost",
        "port": 5432,
        "database": "tasks",
        "user": "tasks",
        "password": "local",
        "ssl": False,
    }


def test_an_ssl_opt_out_in_the_environment_is_respected():
    config = resolve_database_config(
        environ={"DB_SECRET_ARN": SECRET_ARN, "DB_SSL": "false"},
        create_secret_client=lambda region: FakeSecretClient(),
    )

    assert config["ssl"] is False


def test_a_secret_that_is_not_a_json_object_is_rejected():
    with pytest.raises(ValueError, match="not a JSON object"):
        secret_entry_to_config(["not", "a", "mapping"])


def test_a_missing_secret_string_is_rejected():
    class EmptyClient:
        def get_secret_value(self, *, SecretId):
            return {}

    with pytest.raises(ValueError, match="no SecretString"):
        resolve_database_config(
            environ={"DB_SECRET_ARN": SECRET_ARN},
            create_secret_client=lambda region: EmptyClient(),
        )


def test_config_from_environment_defaults_to_the_local_database():
    assert config_from_environment({}) == {
        "host": None,
        "port": 5432,
        "database": "tasks",
        "user": "tasks",
        "password": None,
        "ssl": False,
    }
