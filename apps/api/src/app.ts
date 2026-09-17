import express, { type Express } from 'express';
import { InMemoryDashboardService, type DashboardService } from '@v3/dashboard';
import { GovernanceError, InMemoryDecisionService, type DecisionService } from '@v3/governance';
import { healthReport } from '@v3/shared';

export function createApp(
  options: { readonly decisions?: DecisionService; readonly dashboard?: DashboardService } = {},
): Express {
  const app = express();
  const decisions = options.decisions ?? new InMemoryDecisionService();
  const dashboard = options.dashboard ?? new InMemoryDashboardService();
  app.disable('x-powered-by');
  app.use(express.json({ limit: '1mb' }));
  app.get('/health', (_request, response) => response.json(healthReport('api')));
  app.get('/projects/:projectId/dashboard', async (request, response, next) => {
    try {
      const snapshot = await dashboard.getDashboard(request.params.projectId ?? '');
      if (snapshot === null) {
        response.status(404).json({ error: 'Project dashboard not found' });
        return;
      }
      response.json(snapshot);
    } catch (error) {
      next(error);
    }
  });
  app.get('/projects/:projectId/decisions', async (request, response, next) => {
    try {
      response.json({ decisions: await decisions.listPending(request.params.projectId ?? '') });
    } catch (error) {
      next(error);
    }
  });
  app.post('/projects/:projectId/decisions/:requestId', async (request, response, next) => {
    try {
      const body = request.body as Readonly<Record<string, unknown>>;
      const result = await decisions.decide({
        id: typeof body.id === 'string' ? body.id : '',
        requestId: request.params.requestId ?? '',
        projectId: request.params.projectId ?? '',
        selectedOptionId: typeof body.selectedOptionId === 'string' ? body.selectedOptionId : '',
        userWords: typeof body.userWords === 'string' ? body.userWords : '',
        submittedAt: new Date(),
      });
      response.status(201).json(result);
    } catch (error) {
      next(error);
    }
  });
  app.post('/projects/:projectId/delegations/:delegationId/revoke', async (request, response, next) => {
    try {
      const body = request.body as Readonly<Record<string, unknown>>;
      const result = await decisions.revoke({
        projectId: request.params.projectId ?? '',
        delegationId: request.params.delegationId ?? '',
        userWords: typeof body.userWords === 'string' ? body.userWords : '',
      });
      response.status(200).json(result);
    } catch (error) {
      next(error);
    }
  });
  app.use((error: unknown, _request: express.Request, response: express.Response, next: express.NextFunction) => {
    if (error instanceof GovernanceError) {
      response.status(400).json({ error: error.message });
      return;
    }
    next(error);
  });
  return app;
}
