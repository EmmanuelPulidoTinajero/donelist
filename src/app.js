const express = require('express');
const { createMemoryMetrics } = require('./metrics');

const APP_VERSION = process.env.APP_VERSION || require('../package.json').version;

function createApp({ pool, version = APP_VERSION, now = () => new Date(), metrics = createMemoryMetrics() }) {
  if (!pool || typeof pool.query !== 'function') {
    throw new Error('A PostgreSQL-compatible pool is required');
  }

  const app = express();
  app.use(express.json());

  app.get('/tasks', async (_req, res) => {
    try {
      const result = await pool.query(
        'SELECT id, title, completed, created_at FROM tasks ORDER BY id ASC'
      );
      res.json(result.rows);
    } catch (error) {
      metrics.increment('DbReadErrors');
      res.status(500).json({ error: 'Unable to load tasks' });
    }
  });

  app.post('/tasks', async (req, res) => {
    const title = typeof req.body?.title === 'string' ? req.body.title.trim() : '';
    if (!title) {
      return res.status(400).json({ error: 'title is required' });
    }

    try {
      const result = await pool.query(
        'INSERT INTO tasks (title) VALUES ($1) RETURNING id, title, completed, created_at',
        [title]
      );
      metrics.increment('TasksCreated');
      return res.status(201).json(result.rows[0]);
    } catch (error) {
      metrics.increment('DbWriteErrors');
      return res.status(500).json({ error: 'Unable to create task' });
    }
  });

  app.get('/version', (_req, res) => {
    res.json({ version });
  });

  app.get('/health', async (_req, res) => {
    try {
      await pool.query('SELECT 1');
      return res.status(200).json({ status: 'OK', version, timestamp: now().toISOString() });
    } catch (error) {
      metrics.increment('DbReadErrors');
      return res.status(503).json({ status: 'FAIL', version, timestamp: now().toISOString() });
    }
  });

  return app;
}

module.exports = { createApp };
