import { execFile } from 'node:child_process';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { afterEach, describe, expect, it } from 'vitest';

import { GitRepositoryInspector } from '@v3/repository';

import { ArtifactStore, InvestigationService } from './index.js';

const exec = promisify(execFile);
const roots: string[] = [];

async function fixture(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'v3-context-'));
  roots.push(root);
  await mkdir(join(root, 'src'));
  await mkdir(join(root, 'tests'));
  await writeFile(join(root, 'AGENTS.md'), '# Preserve tests\n');
  await writeFile(join(root, 'src', 'inventory.ts'), 'export function reserveInventory() { return true; }\n');
  await writeFile(join(root, 'src', 'unrelated.ts'), 'export const color = "blue";\n');
  await writeFile(join(root, 'tests', 'inventory.test.ts'), 'test("inventory", () => true);\n');
  await exec('git', ['init', '-q'], { cwd: root });
  await exec('git', ['config', 'user.email', 'v3@example.invalid'], { cwd: root });
  await exec('git', ['config', 'user.name', 'V3 Test'], { cwd: root });
  await exec('git', ['add', '.'], { cwd: root });
  await exec('git', ['commit', '-qm', 'fixture'], { cwd: root });
  return root;
}

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('InvestigationService', () => {
  it('builds deterministic task-grounded context within the declared budget', async () => {
    const root = await fixture();
    const service = new InvestigationService(new GitRepositoryInspector(root));
    const report = await service.investigate('change inventory reservation', {
      maxFiles: 3,
      maxBytes: 4096,
      maxBytesPerFile: 2048,
    });

    expect(report.relevantFiles.map(({ path }) => path)).toEqual([
      'AGENTS.md',
      'tests/inventory.test.ts',
      'src/inventory.ts',
    ]);
    expect(report.contextBytes).toBeLessThanOrEqual(4096);
    expect(report.relatedTests).toEqual(['tests/inventory.test.ts']);
  });

  it('persists a content-addressed investigation artifact', async () => {
    const root = await fixture();
    const service = new InvestigationService(new GitRepositoryInspector(root));
    const report = await service.investigate('inventory');
    const artifact = await new ArtifactStore(join(root, '.v3-artifacts')).persistInvestigation(report);

    expect(artifact.sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(JSON.parse(await readFile(artifact.path, 'utf8'))).toMatchObject({
      task: 'inventory',
      schemaVersion: '0.1',
    });
  });
});
