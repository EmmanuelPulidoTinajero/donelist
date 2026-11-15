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
    """Move the counter file aside before reading it.

    Renaming first means a counter the API writes during this run lands in a
    fresh file instead of being overwritten when the counters are reset.
    """
    if not os.path.exists(path):
        return None
    claimed = f"{path}.{int(time.time() * 1000)}.claimed"
    try:
        os.rename(path, claimed)
    except FileNotFoundError:
        return None
    try:
        return read_counters(claimed)
    finally:
        try:
            os.unlink(claimed)
        except OSError:
            pass


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

    counters = read_counters(args.file) if args.dry_run else claim_counters(args.file)
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

    publish(metric_data, args.namespace, args.region)
    print(f"Published {len(metric_data)} metrics to {args.namespace}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
