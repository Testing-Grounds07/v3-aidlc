import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { mkdir, realpath } from 'node:fs/promises';
import { basename, isAbsolute, relative, resolve } from 'node:path';

export class WorkspaceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'WorkspaceError';
  }
}

interface GitResult { readonly stdout: string; readonly stderr: string }

function runGit(cwd: string, args: readonly string[]): Promise<GitResult> {
  return new Promise((resolvePromise, reject) => {
    execFile('git', args, { cwd, maxBuffer: 10 * 1024 * 1024 }, (error, stdout, stderr) => {
      if (error !== null) {
        reject(new WorkspaceError(`git ${args[0] ?? 'command'} failed: ${stderr.trim() || error.message}`));
        return;
      }
      resolvePromise({ stdout, stderr });
    });
  });
}

function assertContained(root: string, candidate: string): void {
  const path = relative(root, candidate);
  if (path === '' || path.startsWith('..') || isAbsolute(path)) throw new WorkspaceError('Worktree path must be a child of the workspace root');
}

function assertBranch(branch: string): void {
  if (!/^v3\/[a-z0-9][a-z0-9._/-]{0,100}$/.test(branch) || branch.includes('..') || branch.endsWith('/')) {
    throw new WorkspaceError('Branch must be a safe v3/<name> reference');
  }
}

export interface WorktreeSession {
  readonly id: string;
  readonly workPackageId: string;
  readonly repositoryRoot: string;
  readonly worktreePath: string;
  readonly branch: string;
  readonly baseRevision: string;
  readonly headRevision: string;
}

export class GitWorktreeManager {
  private constructor(private readonly repositoryRoot: string, private readonly workspaceRoot: string) {}

  static async open(repositoryRoot: string, workspaceRoot: string): Promise<GitWorktreeManager> {
    const repo = await realpath(repositoryRoot);
    await mkdir(workspaceRoot, { recursive: true });
    const spaces = await realpath(workspaceRoot);
    const top = (await runGit(repo, ['rev-parse', '--show-toplevel'])).stdout.trim();
    if (await realpath(top) !== repo) throw new WorkspaceError('Repository root must be the Git top level');
    if (repo === spaces) throw new WorkspaceError('Workspace root must be separate from the repository checkout');
    return new GitWorktreeManager(repo, spaces);
  }

  async create(input: {
    readonly id: string;
    readonly workPackageId: string;
    readonly branch: string;
    readonly baseRevision: string;
  }): Promise<WorktreeSession> {
    assertBranch(input.branch);
    await runGit(this.repositoryRoot, ['check-ref-format', '--branch', input.branch]);
    const baseRevision = (await runGit(this.repositoryRoot, ['rev-parse', '--verify', `${input.baseRevision}^{commit}`])).stdout.trim();
    const worktreePath = resolve(this.workspaceRoot, input.workPackageId.toLowerCase());
    assertContained(this.workspaceRoot, worktreePath);
    await runGit(this.repositoryRoot, ['worktree', 'add', '-b', input.branch, worktreePath, baseRevision]);
    const headRevision = (await runGit(worktreePath, ['rev-parse', 'HEAD'])).stdout.trim();
    return {
      id: input.id,
      workPackageId: input.workPackageId,
      repositoryRoot: this.repositoryRoot,
      worktreePath,
      branch: input.branch,
      baseRevision,
      headRevision,
    };
  }

  async inspect(session: WorktreeSession): Promise<WorktreeSession & { readonly clean: boolean }> {
    assertContained(this.workspaceRoot, resolve(session.worktreePath));
    const branch = (await runGit(session.worktreePath, ['branch', '--show-current'])).stdout.trim();
    if (branch !== session.branch) throw new WorkspaceError('Worktree branch no longer matches its session');
    const headRevision = (await runGit(session.worktreePath, ['rev-parse', 'HEAD'])).stdout.trim();
    const clean = (await runGit(session.worktreePath, ['status', '--porcelain'])).stdout.trim() === '';
    return { ...session, headRevision, clean };
  }
}

export interface ChangeProposal {
  readonly id: string;
  readonly workPackageId: string;
  readonly title: string;
  readonly body: string;
  readonly baseRevision: string;
  readonly headRevision: string;
  readonly branch: string;
  readonly changedFiles: readonly string[];
  readonly verificationEvidenceIds: readonly string[];
  readonly digest: string;
}

export async function prepareChangeProposal(input: {
  readonly id: string;
  readonly session: WorktreeSession;
  readonly title: string;
  readonly summary: string;
  readonly verificationEvidenceIds: readonly string[];
}): Promise<ChangeProposal> {
  if (input.verificationEvidenceIds.length === 0) throw new WorkspaceError('A change proposal requires verification evidence');
  const headRevision = (await runGit(input.session.worktreePath, ['rev-parse', 'HEAD'])).stdout.trim();
  if (headRevision === input.session.baseRevision) throw new WorkspaceError('A change proposal requires at least one committed change');
  const ancestor = await new Promise<boolean>((resolvePromise) => {
    execFile('git', ['merge-base', '--is-ancestor', input.session.baseRevision, headRevision], { cwd: input.session.worktreePath }, (error) => resolvePromise(error === null));
  });
  if (!ancestor) throw new WorkspaceError('The proposal head is not based on the declared base revision');
  const changedFiles = (await runGit(input.session.worktreePath, ['diff', '--name-only', `${input.session.baseRevision}...${headRevision}`])).stdout.trim().split('\n').filter(Boolean).sort();
  const stat = (await runGit(input.session.worktreePath, ['diff', '--stat', `${input.session.baseRevision}...${headRevision}`])).stdout.trim();
  const body = `${input.summary.trim()}\n\nVerification evidence: ${input.verificationEvidenceIds.join(', ')}\n\n${stat}`.trim();
  const canonical = JSON.stringify({
    id: input.id, workPackageId: input.session.workPackageId, title: input.title, body,
    baseRevision: input.session.baseRevision, headRevision, branch: input.session.branch,
    changedFiles, verificationEvidenceIds: [...input.verificationEvidenceIds],
  });
  return {
    id: input.id, workPackageId: input.session.workPackageId, title: input.title, body,
    baseRevision: input.session.baseRevision, headRevision, branch: input.session.branch,
    changedFiles, verificationEvidenceIds: [...input.verificationEvidenceIds],
    digest: createHash('sha256').update(canonical).digest('hex'),
  };
}

export function findFileConflicts(proposals: readonly ChangeProposal[]): Readonly<Record<string, readonly string[]>> {
  const owners = new Map<string, string[]>();
  for (const proposal of proposals) {
    for (const file of proposal.changedFiles) owners.set(file, [...(owners.get(file) ?? []), proposal.workPackageId]);
  }
  return Object.fromEntries([...owners].filter(([, workPackages]) => workPackages.length > 1).sort(([left], [right]) => left.localeCompare(right)));
}

export const worktreeName = (session: WorktreeSession): string => basename(session.worktreePath);
