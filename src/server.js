const { Pool } = require('pg');
const { createApp } = require('./app');
const { createFileMetrics } = require('./metrics');
const { resolveDatabaseConfig } = require('./secrets');

async function main() {
  const port = Number(process.env.PORT || 3000);

  // Credentials come from Secrets Manager at runtime when DB_SECRET_ARN is set.
  const pool = new Pool(await resolveDatabaseConfig());
  const metrics = createFileMetrics();
  const app = createApp({ pool, metrics });

  const server = app.listen(port, () => {
    console.log(`to-do-list-api listening on port ${port}`);
  });

  async function shutdown(signal) {
    console.log(`${signal} received; shutting down`);
    server.close(async () => {
      await pool.end();
      process.exit(0);
    });
  }

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
}

main().catch((error) => {
  console.error(`to-do-list-api failed to start: ${error.message}`);
  process.exit(1);
});
