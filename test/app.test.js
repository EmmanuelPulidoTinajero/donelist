const test = require('node:test');
const assert = require('node:assert/strict');
const request = require('supertest');
const { createApp } = require('../src/app');

function createPool({ query }) {
  return { query };
}

test('GET /tasks returns persisted tasks', async () => {
  const pool = createPool({ query: async () => ({ rows: [{ id: 1, title: 'Study', completed: false }] }) });
  const response = await request(createApp({ pool })).get('/tasks');
  assert.equal(response.status, 200);
  assert.deepEqual(response.body, [{ id: 1, title: 'Study', completed: false }]);
});

test('POST /tasks validates and persists a title', async () => {
  let queryArgs;
  const pool = createPool({
    query: async (...args) => {
      queryArgs = args;
      return { rows: [{ id: 2, title: 'Ship', completed: false }] };
    }
  });
  const response = await request(createApp({ pool })).post('/tasks').send({ title: ' Ship ' });
  assert.equal(response.status, 201);
  assert.deepEqual(response.body, { id: 2, title: 'Ship', completed: false });
  assert.deepEqual(queryArgs, [
    'INSERT INTO tasks (title) VALUES ($1) RETURNING id, title, completed, created_at',
    ['Ship']
  ]);
});

test('POST /tasks rejects an empty title without querying the database', async () => {
  let called = false;
  const pool = createPool({ query: async () => { called = true; return { rows: [] }; } });
  const response = await request(createApp({ pool })).post('/tasks').send({ title: '  ' });
  assert.equal(response.status, 400);
  assert.deepEqual(response.body, { error: 'title is required' });
  assert.equal(called, false);
});

test('GET /version returns the configured version', async () => {
  const response = await request(createApp({ pool: createPool({ query: async () => ({ rows: [] }) }), version: '2.3.4' })).get('/version');
  assert.equal(response.status, 200);
  assert.deepEqual(response.body, { version: '2.3.4' });
});

test('GET /health reports OK when the database responds', async () => {
  const fixedDate = new Date('2025-01-01T00:00:00.000Z');
  const pool = createPool({ query: async () => ({ rows: [{ '?column?': 1 }] }) });
  const response = await request(createApp({ pool, version: '1.2.3', now: () => fixedDate })).get('/health');
  assert.equal(response.status, 200);
  assert.deepEqual(response.body, { status: 'OK', version: '1.2.3', timestamp: fixedDate.toISOString() });
});

test('GET /health reports FAIL when the database is unavailable', async () => {
  const fixedDate = new Date('2025-01-01T00:00:00.000Z');
  const pool = createPool({ query: async () => { throw new Error('offline'); } });
  const response = await request(createApp({ pool, now: () => fixedDate })).get('/health');
  assert.equal(response.status, 503);
  assert.deepEqual(response.body, { status: 'FAIL', version: '1.0.0', timestamp: fixedDate.toISOString() });
});
