export interface DashboardWorkItem {
  readonly id: string;
  readonly title: string;
  readonly workstream: string;
  readonly stage: string;
  readonly mode: string;
  readonly posture: string;
  readonly status: string;
  readonly progress: number;
  readonly summary: string;
  readonly lastUpdatedAt: Date;
}

export interface DashboardDecision {
  readonly id: string;
  readonly headline: string;
  readonly question: string;
  readonly impact: string;
  readonly optionCount: number;
  readonly requestedAt: Date;
}

export interface ProjectDashboard {
  readonly project: { readonly id: string; readonly name: string; readonly outcome: string; readonly status: string };
  readonly summary: { readonly completed: number; readonly active: number; readonly waiting: number; readonly blocked: number };
  readonly work: readonly DashboardWorkItem[];
  readonly decisions: readonly DashboardDecision[];
  readonly evidence: { readonly passed: number; readonly failed: number; readonly inconclusive: number; readonly updatedAt: Date };
}

export interface DashboardService {
  getDashboard(projectId: string): Promise<ProjectDashboard | null>;
}

export class InMemoryDashboardService implements DashboardService {
  constructor(private readonly dashboards: readonly ProjectDashboard[] = []) {}
  async getDashboard(projectId: string): Promise<ProjectDashboard | null> {
    return this.dashboards.find(({ project }) => project.id === projectId) ?? null;
  }
}

export function summarizeWork(work: readonly DashboardWorkItem[]): ProjectDashboard['summary'] {
  const terminal = new Set(['accepted', 'closed']);
  const waiting = new Set(['planned', 'eligible', 'repair_required', 'decision_required']);
  return work.reduce(
    (summary, item) => {
      if (terminal.has(item.status)) summary.completed += 1;
      else if (item.status === 'blocked') summary.blocked += 1;
      else if (waiting.has(item.status)) summary.waiting += 1;
      else summary.active += 1;
      return summary;
    },
    { completed: 0, active: 0, waiting: 0, blocked: 0 },
  );
}

export function plainStatus(status: string): string {
  const labels: Readonly<Record<string, string>> = {
    planned: 'Planned', eligible: 'Ready to start', running: 'In progress', evidence_pending: 'Gathering proof',
    verifying: 'Running checks', reviewing: 'Under review', repair_required: 'Needs a fix',
    decision_required: 'Waiting for your choice', blocked: 'Blocked', accepted: 'Approved', closed: 'Complete',
  };
  return labels[status] ?? 'Status unavailable';
}
