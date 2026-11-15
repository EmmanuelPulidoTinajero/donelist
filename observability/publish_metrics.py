#!/usr/bin/env python3
"""Publish the to-do-list API counters to CloudWatch.

The API increments counters for failed database reads, failed database writes and
created tasks. This publisher is the only component that talks to CloudWatch, and
it does so with boto3 ``put_metric_data`` as the assignment requires.
"""

import argparse
import json
import os
import sys
import time

DEFAULT_METRICS_FILE = "/var/lib/to-do-list-api/metrics.json"
DEFAULT_NAMESPACE = "ToDoListApi"
METRIC_NAMES = ("DbReadErrors", "DbWriteErrors", "TasksCreated")


def read_counters(path):
    """Return the counters stored at ``path``, or None when absent or unusable."""
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def claim_counters(path):
    """Move the counter file aside and return ``(counters, claimed_path)``.

    Renaming first means a counter the API writes during this run lands in a
    fresh file instead of being overwritten when the counters are reset. The
    claimed file is kept until the publish succeeds: a failed
    ``put_metric_data`` must not destroy the interval's datapoints, because the
    RDS error alarms depend on them.
    """
    if not os.path.exists(path):
        return None, None
    claimed = f"{path}.{int(time.time() * 1000)}.claimed"
    try:
        os.rename(path, claimed)
    except FileNotFoundError:
        return None, None
    counters = read_counters(claimed)
    if not counters:
        release_claim(claimed)
        return None, None
    return counters, claimed


def release_claim(claimed_path):
    """Drop a claimed counter file that was published or is unusable."""
    if not claimed_path:
        return
    try:
        os.unlink(claimed_path)
    except OSError:
        pass


def write_counters(path, counters):
    """Write counters atomically so a reader never sees a partial file."""
    temporary = f"{path}.{os.getpid()}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(counters, handle, sort_keys=True)
    os.replace(temporary, path)


def restore_counters(claimed_path, path):
    """Merge a failed claim back into the live file so the next run retries it.

    Increments the API wrote while the publish was failing are added on top, so
    no datapoint is lost and none is counted twice.
    """
    claimed = read_counters(claimed_path) or {}
    merged = dict(read_counters(path) or {})
    for name, value in claimed.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        previous = merged.get(name, 0)
        if isinstance(previous, bool) or not isinstance(previous, (int, float)):
            previous = 0
        merged[name] = previous + value
    write_counters(path, merged)
    release_claim(claimed_path)


def build_metric_data(counters):
    metric_data = []
    for name in METRIC_NAMES:
        value = counters.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        metric_data.append({"MetricName": name, "Value": float(value), "Unit": "Count"})
    return metric_data


def publish(metric_data, namespace, region):
    import boto3

    client = boto3.client("cloudwatch", region_name=region)
    client.put_metric_data(Namespace=namespace, MetricData=metric_data)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Publish to-do-list API counters to CloudWatch.")
    parser.add_argument("--file", default=os.environ.get("METRICS_FILE", DEFAULT_METRICS_FILE))
    parser.add_argument("--namespace", default=os.environ.get("METRICS_NAMESPACE", DEFAULT_NAMESPACE))
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the put_metric_data payload without calling AWS or resetting the counters.",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        counters, claimed_path = read_counters(args.file), None
    else:
        counters, claimed_path = claim_counters(args.file)
    if not counters:
        print(f"No counters at {args.file}; nothing to publish")
        return 0

    metric_data = build_metric_data(counters)
    if not metric_data:
        print(f"No usable counters in {args.file}; nothing to publish")
        return 0

    payload = {"Namespace": args.namespace, "MetricData": metric_data}
    if args.dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    try:
        publish(metric_data, args.namespace, args.region)
    except Exception:
        try:
            restore_counters(claimed_path, args.file)
        except OSError as error:
            print(f"Could not restore counters from {claimed_path}: {error}", file=sys.stderr)
        print(f"Publish failed; counters kept in {args.file} for the next run", file=sys.stderr)
        raise
    release_claim(claimed_path)
    print(f"Published {len(metric_data)} metrics to {args.namespace}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
