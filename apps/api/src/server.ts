import { readEnvironment } from '@v3/config';
import { ProjectRepository, createDatabaseClient } from '@v3/database';
import { createApp } from './app.js';

const environment = readEnvironment();
const database = createDatabaseClient();
const app = createApp({ dashboard: new ProjectRepository(database) });

app.listen(environment.V3_API_PORT, '127.0.0.1', () => {
  process.stdout.write(`V3 API listening on http://127.0.0.1:${environment.V3_API_PORT}\n`);
});

for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.once(signal, () => {
    void database.$disconnect().finally(() => process.exit(0));
  });
}
