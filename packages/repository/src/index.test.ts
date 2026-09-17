import { execFile } from 'node:child_process';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { afterEach, describe, expect, it } from 'vitest';

import { GitRepositoryInspector, RepositoryInspectionError } from './index.js';

const exec = promisify(execFile);
const roots: string[] = [];

async function fixture(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'v3-repository-'));
  roots.push(root);
  await mkdir(join(root, 'src'));
  await mkdir(join(root, 'tests'));
  await writeFile(join(root, 'AGENTS.md'), '# Rules\n');
  await writeFile(join(root, 'src', 'feature.ts'), 'export const feature = true;\n');
  await writeFile(join(root, 'tests', 'feature.test.ts'), 'test("feature", () => true);\n');
  await writeFile(join(root, '.env'), 'SECRET=not-for-context\n');
  await exec('git', ['init', '-q'], { cwd: root });
  await exec('git', ['config', 'user.email', 'v3@example.invalid'], { cwd: root });
  await exec('git', ['config', 'user.name', 'V3 Test'], { cwd: root });
  await exec('git', ['add', 'AGENTS.md', 'src/feature.ts', 'tests/feature.test.ts'], { cwd: root });
  await exec('git', ['commit', '-qm', 'fixture'], { cwd: root });
  return root;
}

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('GitRepositoryInspector', () => {
  it('reports revision, instructions, source, and tests without secret files', async () => {
    const inspector = new GitRepositoryInspector(await fixture());
    const snapshot = await inspector.inspect();
    expect(snapshot.headRevision).toMatch(/^[0-9a-f]{40}$/);
    expect(snapshot.instructions).toEqual(['AGENTS.md']);
    expect(snapshot.files.map(({ path }) => path)).toEqual([
      'AGENTS.md', 'src/feature.ts', 'tests/feature.test.ts',
    ]);
  });

  it('prevents paths from escaping the repository', async () => {
    const inspector = new GitRepositoryInspector(await fixture());
    await expect(inspector.readTextFile('../outside.txt')).rejects.toBeInstanceOf(
      RepositoryInspectionError,
    );
  });
});
