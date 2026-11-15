const test = require('node:test');
const assert = require('node:assert/strict');
const { resolveDatabaseConfig } = require('../src/secrets');

const SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:000000000000:secret:to-do-list-api/database';

test('resolveDatabaseConfig reads the secret from Secrets Manager at runtime', async () => {
  const requested = [];
  const client = {
    async getSecretValue(input) {
      requested.push(input);
      return {
        SecretString: JSON.stringify({
          host: 'db.example.internal',
          port: 5432,
          database: 'tasks',
          username: 'tasks_app',
          password: 'p@ss-from-secret'
        })
      };
    },
    destroy() {}
  };

  const config = await resolveDatabaseConfig({
    env: { DB_SECRET_ARN: SECRET_ARN, DB_PASSWORD: 'stale-environment-password' },
    createSecretClient: () => client
  });

  assert.deepEqual(requested, [{ SecretId: SECRET_ARN }]);
  assert.equal(config.host, 'db.example.internal');
  assert.equal(config.port, 5432);
  assert.equal(config.database, 'tasks');
  assert.equal(config.user, 'tasks_app');
  assert.equal(config.password, 'p@ss-from-secret');
});

test('resolveDatabaseConfig falls back to DB_* environment variables without a secret ARN', async () => {
  const config = await resolveDatabaseConfig({
    env: { DB_HOST: 'localhost', DB_USER: 'tasks', DB_PASSWORD: 'local' },
    createSecretClient: () => {
      throw new Error('Secrets Manager must not be called without DB_SECRET_ARN');
    }
  });

  assert.equal(config.host, 'localhost');
  assert.equal(config.port, 5432);
  assert.equal(config.database, 'tasks');
  assert.equal(config.user, 'tasks');
  assert.equal(config.password, 'local');
});
