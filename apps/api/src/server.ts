import { readEnvironment } from '@v3/config';
import { createApp } from './app.js';

const environment = readEnvironment();
const app = createApp();

app.listen(environment.V3_API_PORT, '127.0.0.1', () => {
  process.stdout.write(`V3 API listening on http://127.0.0.1:${environment.V3_API_PORT}\n`);
});
