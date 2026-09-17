import { execFile as execFileCallback } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { afterEach, describe, expect, it } from 'vitest';

import { GitWorktreeManager, WorkspaceError, findFileConflicts, prepareChangeProposal } from './index.js';

const execFile = promisify(execFileCallback);
const roots: string[] = [];

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), 'v3-workspace-'));
  roots.push(root);
  const repo = join(root, 'repo');
  const spaces = join(root, 'worktrees');
  await execFile('git', ['init', repo]);
  await execFile('git', ['config', 'user.name', 'V3 Test'], { cwd: repo });
  await execFile('git', ['config', 'user.email', 'v3@example.test'], { cwd: repo });
  await writeFile(join(repo, 'README.md'), 'base\n');
  await execFile('git', ['add', 'README.md'], { cwd: repo });
  await execFile('git', ['commit', '-m', 'base'], { cwd: repo });
  const base = (await execFile('git', ['rev-parse', 'HEAD'], { cwd: repo })).stdout.trim();
  return { repo, spaces, base };
}

afterEach(async () => { await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true }))); });

describe('GitWorktreeManager', () => {
  it('creates and inspects a real isolated branch and worktree', async () => {
    const { repo, spaces, base } = await fixture();
    const manager = await GitWorktreeManager.open(repo, spaces);
    const session = await manager.create({ id: 'WT-1', workPackageId: 'WP-1', branch: 'v3/wp-1', baseRevision: base });
    expect(session).toMatchObject({ branch: 'v3/wp-1', baseRevision: base, headRevision: base });
    await expect(manager.inspect(session)).resolves.toMatchObject({ clean: true });
  });

  it('rejects unsafe branch names before invoking Git', async () => {
    const { repo, spaces, base } = await fixture();
    const manager = await GitWorktreeManager.open(repo, spaces);
    await expect(manager.create({ id: 'WT-1', workPackageId: 'WP-1', branch: '--upload-pack=bad', baseRevision: base })).rejects.toThrow(WorkspaceError);
  });

  it('prepares a revision-bound proposal with evidence', async () => {
    const { repo, spaces, base } = await fixture();
    const manager = await GitWorktreeManager.open(repo, spaces);
    const session = await manager.create({ id: 'WT-1', workPackageId: 'WP-1', branch: 'v3/wp-1', baseRevision: base });
    await writeFile(join(session.worktreePath, 'feature.txt'), 'implemented\n');
    await execFile('git', ['add', 'feature.txt'], { cwd: session.worktreePath });
    await execFile('git', ['commit', '-m', 'Implement feature'], { cwd: session.worktreePath });
    const proposal = await prepareChangeProposal({ id: 'PROP-1', session, title: 'Implement feature', summary: 'Adds the bounded feature.', verificationEvidenceIds: ['EVID-1'] });
    expect(proposal.changedFiles).toEqual(['feature.txt']);
    expect(proposal.headRevision).not.toBe(base);
    expect(proposal.digest).toMatch(/^[a-f0-9]{64}$/);
  });
});

describe('findFileConflicts', () => {
  it('reports overlapping files across proposals', () => {
    const base = { id: 'P', title: 't', body: 'b', baseRevision: 'base', headRevision: 'head', branch: 'v3/a', verificationEvidenceIds: ['E'], digest: 'd' };
    expect(findFileConflicts([
      { ...base, workPackageId: 'WP-1', changedFiles: ['a.ts', 'shared.ts'] },
      { ...base, id: 'P2', workPackageId: 'WP-2', changedFiles: ['b.ts', 'shared.ts'] },
    ])).toEqual({ 'shared.ts': ['WP-1', 'WP-2'] });
  });
});
