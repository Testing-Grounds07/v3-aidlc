import express, { type Express } from 'express';
import { healthReport } from '@v3/shared';

export function createApp(): Express {
  const app = express();
  app.disable('x-powered-by');
  app.use(express.json({ limit: '1mb' }));
  app.get('/health', (_request, response) => response.json(healthReport('api')));
  return app;
}
