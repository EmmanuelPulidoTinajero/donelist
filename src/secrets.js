const DEFAULT_PORT = 5432;

// Connection settings published directly through the environment. Used for
// local runs and tests; production resolves them from Secrets Manager instead.
function configFromEnvironment(env = process.env) {
  return {
    host: env.DB_HOST,
    port: Number(env.DB_PORT || DEFAULT_PORT),
    database: env.DB_NAME || 'tasks',
    user: env.DB_USER || 'tasks',
    password: env.DB_PASSWORD,
    ssl: env.DB_SSL === 'true' ? { rejectUnauthorized: false } : undefined
  };
}

function secretEntryToConfig(secret, env = process.env) {
  return {
    host: secret.host,
    port: Number(secret.port || DEFAULT_PORT),
    database: secret.database,
    user: secret.username,
    password: secret.password,
    ssl: env.DB_SSL === 'false' ? undefined : { rejectUnauthorized: false }
  };
}

function defaultSecretClient(env = process.env) {
  const { SecretsManagerClient } = require('@aws-sdk/client-secrets-manager');
  const region = env.AWS_REGION || env.AWS_DEFAULT_REGION;
  return region ? new SecretsManagerClient({ region }) : new SecretsManagerClient();
}

// The application reads its own credentials at runtime. DB_SECRET_ARN is the
// only database input the deployment supplies; the DB_* variables remain a
// fallback so the service can also run without Secrets Manager.
async function resolveDatabaseConfig({ env = process.env, createSecretClient = defaultSecretClient } = {}) {
  if (!env.DB_SECRET_ARN) {
    return configFromEnvironment(env);
  }

  const client = createSecretClient(env);
  try {
    const response = await client.getSecretValue({ SecretId: env.DB_SECRET_ARN });
    if (!response || typeof response.SecretString !== 'string') {
      throw new Error('Secrets Manager returned no SecretString');
    }
    return secretEntryToConfig(JSON.parse(response.SecretString), env);
  } finally {
    if (typeof client.destroy === 'function') {
      client.destroy();
    }
  }
}

module.exports = { configFromEnvironment, secretEntryToConfig, resolveDatabaseConfig };
