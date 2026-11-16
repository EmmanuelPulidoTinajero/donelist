"""Custom CloudWatch metrics, counted in the app and published with boto3.

The three counters are the ones the assignment asks for: two instrumented
metrics about reading and writing RDS, and one about the to-do-list behaviour
itself. They are aggregated in memory and flushed by a background thread, so a
request never waits on CloudWatch and a CloudWatch outage never fails a request.
"""

from __future__ import annotations

import threading

METRIC_NAMES = ("DbReadErrors", "DbWriteErrors", "TasksCreated")
METRIC_UNIT = "Count"


class Counters:
    """Thread-safe counters shared by the request handlers and the publisher."""

    def __init__(self, names=METRIC_NAMES):
        self._names = tuple(names)
        self._lock = threading.Lock()
        self._values = {name: 0 for name in self._names}

    def _assert_known(self, name: str) -> None:
        if name not in self._values:
            raise ValueError(f"Unknown metric: {name}")

    def increment(self, name: str, amount: int = 1) -> int:
        self._assert_known(name)
        with self._lock:
            self._values[name] += amount
            return self._values[name]

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._values)

    def drain(self) -> dict[str, int]:
        """Return the current values and reset them to zero atomically."""
        with self._lock:
            drained = dict(self._values)
            for name in self._values:
                self._values[name] = 0
            return drained

    def restore(self, values: dict[str, int]) -> None:
        """Add values back after a failed publish so no datapoint is lost."""
        with self._lock:
            for name, value in values.items():
                if name in self._values and value:
                    self._values[name] += value


class CloudWatchPublisher:
    """Flushes the counters to CloudWatch with ``put_metric_data``."""

    def __init__(self, counters: Counters, *, namespace: str, client=None, flush_seconds: float = 60.0, region: str | None = None):
        self._counters = counters
        self._namespace = namespace
        self._client = client
        self._region = region
        self._flush_seconds = flush_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._warned = False

    def _cloudwatch(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("cloudwatch", region_name=self._region)
        return self._client

    def build_metric_data(self, counters: dict[str, int]) -> list[dict]:
        return [
            {"MetricName": name, "Value": float(counters.get(name, 0)), "Unit": METRIC_UNIT}
            for name in METRIC_NAMES
        ]

    def flush_once(self) -> bool:
        """Publish the drained counters. Returns True when a call was made.

        A failed publish puts the values back, because a dropped datapoint can
        keep a CloudWatch alarm from ever reaching its threshold.
        """
        drained = self._counters.drain()
        if not any(drained.values()):
            return False

        try:
            self._cloudwatch().put_metric_data(
                Namespace=self._namespace, MetricData=self.build_metric_data(drained)
            )
        except Exception as error:  # noqa: BLE001 - monitoring must not crash the app
            self._counters.restore(drained)
            if not self._warned:
                # Log once: a broken publisher would otherwise flood the journal.
                print(f"CloudWatch publish failed: {error}", flush=True)
                self._warned = True
            return False

        self._warned = False
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            self.flush_once()
            self._stop.wait(self._flush_seconds)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="cloudwatch-publisher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
