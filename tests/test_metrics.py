"""Counters and the boto3 publisher.

These tests pin the two properties the CloudWatch alarms depend on: a datapoint
is never lost when the publish fails, and a published interval is never counted
twice.
"""

from __future__ import annotations

import pytest

from metrics import CloudWatchPublisher, Counters, METRIC_NAMES


class FakeCloudWatch:
    def __init__(self, error=None):
        self.calls: list[dict] = []
        self.error = error

    def put_metric_data(self, **kwargs):
        if self.error:
            raise self.error
        self.calls.append(kwargs)


def publisher_for(counters, client, namespace="ToDoListApi"):
    return CloudWatchPublisher(
        counters, namespace=namespace, client=client, flush_seconds=3600, region="us-east-1"
    )


def test_counters_accumulate_and_snapshot():
    counters = Counters()

    counters.increment("TasksCreated")
    counters.increment("TasksCreated")

    assert counters.snapshot() == {"DbReadErrors": 0, "DbWriteErrors": 0, "TasksCreated": 2}


def test_drain_resets_the_counters_so_the_next_interval_starts_at_zero():
    counters = Counters()
    counters.increment("DbWriteErrors", 2)

    assert counters.drain()["DbWriteErrors"] == 2
    counters.increment("DbWriteErrors")
    assert counters.snapshot()["DbWriteErrors"] == 1


def test_counters_reject_an_unknown_metric_name():
    counters = Counters()

    with pytest.raises(ValueError, match="Unknown metric: NotAMetric"):
        counters.increment("NotAMetric")
    assert counters.snapshot() == {"DbReadErrors": 0, "DbWriteErrors": 0, "TasksCreated": 0}


def test_restore_adds_values_back_after_a_failed_publish():
    counters = Counters()
    counters.increment("DbReadErrors", 4)

    drained = counters.drain()
    counters.restore(drained)

    assert counters.snapshot()["DbReadErrors"] == 4


def test_flush_publishes_every_metric_in_the_namespace():
    counters = Counters()
    counters.increment("TasksCreated", 3)
    client = FakeCloudWatch()
    publisher = publisher_for(counters, client)

    assert publisher.flush_once() is True

    assert len(client.calls) == 1
    payload = client.calls[0]
    assert payload["Namespace"] == "ToDoListApi"
    assert [item["MetricName"] for item in payload["MetricData"]] == list(METRIC_NAMES)
    assert {item["MetricName"]: item["Value"] for item in payload["MetricData"]} == {
        "DbReadErrors": 0.0,
        "DbWriteErrors": 0.0,
        "TasksCreated": 3.0,
    }
    assert {item["Unit"] for item in payload["MetricData"]} == {"Count"}
    assert counters.snapshot()["TasksCreated"] == 0


def test_flush_without_counters_does_not_call_cloudwatch():
    client = FakeCloudWatch()
    publisher = publisher_for(Counters(), client)

    assert publisher.flush_once() is False
    assert client.calls == []


def test_flush_keeps_the_counters_when_cloudwatch_fails():
    counters = Counters()
    counters.increment("DbWriteErrors", 5)
    client = FakeCloudWatch(error=RuntimeError("AccessDenied"))
    publisher = publisher_for(counters, client)

    assert publisher.flush_once() is False
    assert counters.snapshot()["DbWriteErrors"] == 5


def test_flush_publishes_the_kept_counters_once_cloudwatch_recovers():
    counters = Counters()
    counters.increment("DbWriteErrors", 5)
    client = FakeCloudWatch(error=RuntimeError("AccessDenied"))
    publisher = publisher_for(counters, client)
    publisher.flush_once()

    client.error = None
    assert publisher.flush_once() is True

    assert {item["MetricName"]: item["Value"] for item in client.calls[0]["MetricData"]}[
        "DbWriteErrors"
    ] == 5.0
    assert counters.snapshot()["DbWriteErrors"] == 0


def test_flush_does_not_republish_the_previous_interval():
    counters = Counters()
    counters.increment("TasksCreated", 2)
    client = FakeCloudWatch()
    publisher = publisher_for(counters, client)

    publisher.flush_once()
    assert publisher.flush_once() is False

    assert len(client.calls) == 1
