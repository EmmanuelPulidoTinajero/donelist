"""Tests for the CloudWatch publisher.

The publisher claims the counter file before publishing so that increments the API
writes during the run are not overwritten. These tests pin the failure path: a
failed ``put_metric_data`` must not destroy the interval's counters, because the
RDS error alarms depend on those datapoints reaching CloudWatch.
"""

import importlib.util
import json
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "observability" / "publish_metrics.py"
SPEC = importlib.util.spec_from_file_location("publish_metrics", MODULE_PATH)
publish_metrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_metrics)

NAMESPACE = "ToDoListApi"
REGION = "us-east-1"


class PublishMetricsTest(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(self.enterContext(_temp_dir())) / "metrics.json"
        self.published = []
        self.original_publish = publish_metrics.publish

    def tearDown(self):
        publish_metrics.publish = self.original_publish

    def write_counters(self, counters):
        self.path.write_text(json.dumps(counters), encoding="utf-8")

    def stub_publish(self, failure=None):
        def fake_publish(metric_data, namespace, region):
            if failure is not None:
                raise failure
            self.published.append({item["MetricName"]: item["Value"] for item in metric_data})

        publish_metrics.publish = fake_publish

    def run_main(self):
        return publish_metrics.main(["--file", str(self.path), "--namespace", NAMESPACE, "--region", REGION])

    def claimed_files(self):
        return sorted(self.path.parent.glob("metrics.json.*.claimed"))

    def test_failed_publish_keeps_counters_for_the_next_run(self):
        self.write_counters({"DbReadErrors": 2, "DbWriteErrors": 1, "TasksCreated": 5})
        self.stub_publish(failure=RuntimeError("AccessDenied"))

        with self.assertRaises(RuntimeError):
            self.run_main()

        self.assertEqual({"DbReadErrors": 2, "DbWriteErrors": 1, "TasksCreated": 5}, publish_metrics.read_counters(self.path))

        self.stub_publish()
        self.run_main()
        self.assertEqual([{"DbReadErrors": 2.0, "DbWriteErrors": 1.0, "TasksCreated": 5.0}], self.published)

    def test_failed_publish_merges_increments_written_during_the_run(self):
        self.write_counters({"DbReadErrors": 2, "TasksCreated": 5})
        self.stub_publish(failure=RuntimeError("Throttling"))

        def fail_then_increment(metric_data, namespace, region):
            self.write_counters({"TasksCreated": 1})
            raise RuntimeError("Throttling")

        publish_metrics.publish = fail_then_increment
        with self.assertRaises(RuntimeError):
            self.run_main()

        self.assertEqual({"DbReadErrors": 2, "TasksCreated": 6}, publish_metrics.read_counters(self.path))

    def test_successful_publish_resets_the_interval_and_leaves_no_claimed_file(self):
        self.write_counters({"TasksCreated": 3})
        self.stub_publish()

        self.assertEqual(0, self.run_main())

        self.assertEqual([{"DbReadErrors": 0.0, "DbWriteErrors": 0.0, "TasksCreated": 3.0}], self.published)
        self.assertIsNone(publish_metrics.read_counters(self.path))
        self.assertEqual([], self.claimed_files())

    def test_dry_run_does_not_consume_the_counters(self):
        self.write_counters({"TasksCreated": 4})

        self.assertEqual(0, publish_metrics.main(["--file", str(self.path), "--dry-run"]))

        self.assertEqual({"TasksCreated": 4}, publish_metrics.read_counters(self.path))
        self.assertEqual([], self.claimed_files())


def _temp_dir():
    import tempfile

    return tempfile.TemporaryDirectory()


if __name__ == "__main__":
    unittest.main()
