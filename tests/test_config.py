"""Environment handling: the deployed port, version and metric flush window."""

from __future__ import annotations

from config import Settings


def test_defaults_match_the_published_contract():
    settings = Settings.from_env({})

    assert settings.port == 8000
    assert settings.version == "1.0.0"
    assert settings.db_secret_arn is None
    assert settings.db_ssl is True
    assert settings.metrics_namespace == "ToDoListApi"


def test_every_value_can_come_from_the_environment():
    settings = Settings.from_env(
        {
            "PORT": "9001",
            "APP_VERSION": "1.4.2",
            "AWS_REGION": "us-east-1",
            "DB_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:1:secret:x",
            "DB_SSL": "false",
            "METRICS_NAMESPACE": "Custom",
            "METRICS_FLUSH_SECONDS": "15",
        }
    )

    assert settings.port == 9001
    assert settings.version == "1.4.2"
    assert settings.aws_region == "us-east-1"
    assert settings.db_ssl is False
    assert settings.metrics_namespace == "Custom"
    assert settings.metrics_flush_seconds == 15.0


def test_an_unparseable_flush_window_falls_back_to_the_default():
    assert Settings.from_env({"METRICS_FLUSH_SECONDS": "soon"}).metrics_flush_seconds == 60.0
