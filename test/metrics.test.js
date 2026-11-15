const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { createFileMetrics, createMemoryMetrics } = require('../src/metrics');

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'to-do-list-metrics-'));
}

test('createFileMetrics accumulates counters in the durable file', () => {
  const dir = makeTempDir();
  const file = path.join(dir, 'metrics.json');
  const metrics = createFileMetrics({ file, fallback: path.join(dir, 'fallback.json') });

  metrics.increment('TasksCreated');
  metrics.increment('TasksCreated');

  const stored = JSON.parse(fs.readFileSync(file, 'utf8'));
  assert.equal(stored.TasksCreated, 2);
  assert.equal(stored.DbReadErrors, 0);
  assert.deepEqual(metrics.snapshot(), { DbReadErrors: 0, DbWriteErrors: 0, TasksCreated: 2 });
});

test('createFileMetrics starts from zero after the publisher claims the counters', () => {
  const dir = makeTempDir();
  const file = path.join(dir, 'metrics.json');
  const metrics = createFileMetrics({ file, fallback: path.join(dir, 'fallback.json') });

  metrics.increment('DbWriteErrors');
  metrics.increment('DbWriteErrors');
  // What observability/publish_metrics.py does before publishing: move the file aside.
  fs.renameSync(file, path.join(dir, 'metrics.json.claimed'));
  metrics.increment('DbWriteErrors');

  assert.equal(JSON.parse(fs.readFileSync(file, 'utf8')).DbWriteErrors, 1);
});

test('createFileMetrics rejects an unknown metric name and leaves the file untouched', () => {
  const dir = makeTempDir();
  const file = path.join(dir, 'metrics.json');
  const metrics = createFileMetrics({ file, fallback: path.join(dir, 'fallback.json') });

  assert.throws(() => metrics.increment('NotAMetric'), { message: 'Unknown metric: NotAMetric' });
  assert.equal(fs.existsSync(file), false);
});

test('createFileMetrics falls back to the second target when the first cannot be written', () => {
  const dir = makeTempDir();
  const unusable = path.join(dir, 'is-a-directory');
  fs.mkdirSync(unusable);
  const fallback = path.join(dir, 'fallback.json');
  const metrics = createFileMetrics({ file: unusable, fallback });

  assert.equal(metrics.increment('DbReadErrors'), 1);
  assert.equal(JSON.parse(fs.readFileSync(fallback, 'utf8')).DbReadErrors, 1);
  assert.equal(metrics.snapshot().DbReadErrors, 1);
});

test('createMemoryMetrics keeps counters in the process and rejects unknown names', () => {
  const metrics = createMemoryMetrics();

  metrics.increment('TasksCreated', 3);

  assert.deepEqual(metrics.snapshot(), { DbReadErrors: 0, DbWriteErrors: 0, TasksCreated: 3 });
  assert.throws(() => metrics.increment('NotAMetric'), { message: 'Unknown metric: NotAMetric' });
});
