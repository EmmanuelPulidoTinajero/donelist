const fs = require('node:fs');
const path = require('node:path');

const DEFAULT_METRICS_FILE = process.env.METRICS_FILE || '/var/lib/to-do-list-api/metrics.json';
const FALLBACK_METRICS_FILE = '/tmp/to-do-list-api-metrics.json';

const METRIC_NAMES = ['DbReadErrors', 'DbWriteErrors', 'TasksCreated'];

function emptyCounters() {
  const counters = {};
  for (const name of METRIC_NAMES) {
    counters[name] = 0;
  }
  return counters;
}

function assertKnownMetric(name) {
  if (!METRIC_NAMES.includes(name)) {
    throw new Error(`Unknown metric: ${name}`);
  }
}

// Memory-only counters: the default in tests and in any process that does not
// own the durable counters file.
function createMemoryMetrics() {
  const counters = emptyCounters();
  return {
    increment(name, amount = 1) {
      assertKnownMetric(name);
      counters[name] += amount;
      return counters[name];
    },
    snapshot() {
      return { ...counters };
    }
  };
}

// Counters as stored on disk, or null when the file is absent or unusable.
function readCounters(target) {
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(target, 'utf8'));
  } catch (error) {
    return null;
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return null;
  }
  const counters = emptyCounters();
  for (const name of METRIC_NAMES) {
    const value = Number(parsed[name]);
    if (Number.isFinite(value) && value > 0) {
      counters[name] = value;
    }
  }
  return counters;
}

function writeCounters(target, counters) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  const tmpFile = `${target}.${process.pid}.tmp`;
  fs.writeFileSync(tmpFile, `${JSON.stringify(counters)}\n`, 'utf8');
  fs.renameSync(tmpFile, target);
}

// Counters the boto3 publisher reads from disk. The file is the source of truth
// and the publisher claims (renames) it between runs, so every published value
// covers only the events since the previous publish. A failed write never
// breaks the request path: monitoring must not become an outage.
function createFileMetrics({ file = DEFAULT_METRICS_FILE, fallback = FALLBACK_METRICS_FILE } = {}) {
  const targets = [file, fallback];

  function current() {
    for (const target of targets) {
      const counters = readCounters(target);
      if (counters) {
        return counters;
      }
    }
    return emptyCounters();
  }

  return {
    increment(name, amount = 1) {
      assertKnownMetric(name);
      const counters = current();
      counters[name] += amount;
      for (const target of targets) {
        try {
          writeCounters(target, counters);
          return counters[name];
        } catch (error) {
          // Try the next candidate; losing a counter must not fail the request.
        }
      }
      return counters[name];
    },
    snapshot() {
      return current();
    }
  };
}

module.exports = { METRIC_NAMES, DEFAULT_METRICS_FILE, createMemoryMetrics, createFileMetrics };
