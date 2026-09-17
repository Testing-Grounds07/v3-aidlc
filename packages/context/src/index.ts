import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

import type {
  GitRepositoryInspector,
  RepositoryFile,
  RepositorySnapshot,
} from '@v3/repository';

export interface ContextBudget {
  readonly maxFiles: number;
  readonly maxBytes: number;
  readonly maxBytesPerFile: number;
}

export interface InvestigatedFile {
  readonly path: string;
  readonly kind: RepositoryFile['kind'];
  readonly relevanceScore: number;
  readonly reason: string;
  readonly content: string;
  readonly sizeBytes: number;
}

export interface InvestigationReport {
  readonly schemaVersion: '0.1';
  readonly task: string;
  readonly repository: Pick<RepositorySnapshot, 'root' | 'headRevision' | 'branch' | 'clean'>;
  readonly instructions: readonly string[];
  readonly relevantFiles: readonly InvestigatedFile[];
  readonly existingPatterns: readonly string[];
  readonly relatedTests: readonly string[];
  readonly unknowns: readonly string[];
  readonly risks: readonly string[];
  readonly contextBytes: number;
  readonly excludedFileCount: number;
}

export interface PersistedArtifact {
  readonly path: string;
  readonly sha256: string;
  readonly sizeBytes: number;
}

const DEFAULT_BUDGET: ContextBudget = {
  maxFiles: 12,
  maxBytes: 96 * 1024,
  maxBytesPerFile: 24 * 1024,
};

function tokens(value: string): string[] {
  return [...new Set(value.toLowerCase().match(/[a-z0-9_-]{3,}/g) ?? [])];
}

function rank(file: RepositoryFile, taskTokens: readonly string[], instructions: readonly string[]): number {
  const path = file.path.toLowerCase();
  let score = instructions.includes(file.path) ? 100 : 0;
  if (file.kind === 'test') score += 15;
  if (file.kind === 'source') score += 12;
  if (/(^|\/)(readme|package\.json|pyproject\.toml|prisma\/schema\.prisma)/i.test(file.path)) score += 10;
  for (const token of taskTokens) if (path.includes(token)) score += 8;
  return score;
}

export class InvestigationService {
  constructor(private readonly inspector: GitRepositoryInspector) {}

  async investigate(task: string, budget: ContextBudget = DEFAULT_BUDGET): Promise<InvestigationReport> {
    if (task.trim().length === 0) throw new Error('Investigation task must not be empty');
    if (budget.maxFiles < 1 || budget.maxBytes < 1 || budget.maxBytesPerFile < 1) {
      throw new Error('Context budgets must be positive');
    }
    const snapshot = await this.inspector.inspect();
    const taskTokens = tokens(task);
    const ranked = snapshot.files
      .map((file) => ({ file, score: rank(file, taskTokens, snapshot.instructions) }))
      .filter(({ file, score }) => score > 0 || file.kind === 'documentation')
      .sort((left, right) => right.score - left.score || left.file.path.localeCompare(right.file.path));

    const selected: InvestigatedFile[] = [];
    let contextBytes = 0;
    for (const { file, score } of ranked) {
      if (selected.length >= budget.maxFiles) break;
      if (file.sizeBytes > budget.maxBytesPerFile || contextBytes + file.sizeBytes > budget.maxBytes) continue;
      const read = await this.inspector.readTextFile(file.path, budget.maxBytesPerFile);
      if (contextBytes + read.sizeBytes > budget.maxBytes) continue;
      selected.push({
        path: file.path,
        kind: file.kind,
        relevanceScore: score,
        reason:
          snapshot.instructions.includes(file.path)
            ? 'Repository instruction'
            : taskTokens.some((token) => file.path.toLowerCase().includes(token))
              ? 'Path matches the task'
              : `${file.kind} context`,
        content: read.content,
        sizeBytes: read.sizeBytes,
      });
      contextBytes += read.sizeBytes;
    }

    const relatedTests = selected.filter(({ kind }) => kind === 'test').map(({ path }) => path);
    const sourceKinds = new Set(selected.map(({ kind }) => kind));
    const unknowns: string[] = [];
    if (selected.length === 0) unknowns.push('No bounded repository context matched the task.');
    if (relatedTests.length === 0) unknowns.push('No related tracked tests were selected.');
    const risks = snapshot.clean
      ? []
      : ['The repository has uncommitted changes; implementation must preserve unrelated work.'];

    return {
      schemaVersion: '0.1',
      task: task.trim(),
      repository: {
        root: snapshot.root,
        headRevision: snapshot.headRevision,
        branch: snapshot.branch,
        clean: snapshot.clean,
      },
      instructions: snapshot.instructions,
      relevantFiles: selected,
      existingPatterns: [...sourceKinds].sort().map((kind) => `Selected ${kind} files`),
      relatedTests,
      unknowns,
      risks,
      contextBytes,
      excludedFileCount: snapshot.files.length - selected.length,
    };
  }
}

export class ArtifactStore {
  constructor(private readonly root: string) {}

  async persistInvestigation(report: InvestigationReport): Promise<PersistedArtifact> {
    const content = `${JSON.stringify(report, null, 2)}\n`;
    const sha256 = createHash('sha256').update(content).digest('hex');
    const directory = resolve(this.root, 'investigations');
    const path = resolve(directory, `${sha256}.json`);
    await mkdir(directory, { recursive: true });
    await writeFile(path, content, { encoding: 'utf8', flag: 'wx' }).catch((error: unknown) => {
      if (!(error instanceof Error) || !('code' in error) || error.code !== 'EEXIST') throw error;
    });
    return { path, sha256, sizeBytes: Buffer.byteLength(content) };
  }
}
