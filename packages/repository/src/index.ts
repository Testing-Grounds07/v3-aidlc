import { execFile } from 'node:child_process';
import { readFile, stat } from 'node:fs/promises';
import { isAbsolute, relative, resolve, sep } from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

export interface RepositoryFile {
  readonly path: string;
  readonly sizeBytes: number;
  readonly kind: 'source' | 'test' | 'documentation' | 'configuration' | 'other';
}

export interface RepositorySnapshot {
  readonly root: string;
  readonly headRevision: string;
  readonly branch: string;
  readonly clean: boolean;
  readonly instructions: readonly string[];
  readonly files: readonly RepositoryFile[];
}

export interface FileContent {
  readonly path: string;
  readonly content: string;
  readonly sizeBytes: number;
}

export class RepositoryInspectionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RepositoryInspectionError';
  }
}

const blockedNames = /(^|\/)(\.env($|\.)|\.git\/|node_modules\/|dist\/|.*\.(pem|key|p12|pfx)$)/i;

function classify(path: string): RepositoryFile['kind'] {
  if (/(^|\/)(test|tests|__tests__)(\/|$)|\.test\.[^.]+$|\.spec\.[^.]+$/.test(path)) return 'test';
  if (/(^|\/)docs?\/|\.md$/i.test(path)) return 'documentation';
  if (/(^|\/)(package\.json|tsconfig.*\.json|.*\.config\.[^.]+|\.github\/|prisma\/)/.test(path)) return 'configuration';
  if (/\.(ts|tsx|js|jsx|py|go|rs|java|kt|rb|cs|sql|css|html)$/i.test(path)) return 'source';
  return 'other';
}

function withinRoot(root: string, candidate: string): boolean {
  const child = relative(root, candidate);
  return child === '' || (!child.startsWith(`..${sep}`) && child !== '..' && !isAbsolute(child));
}

export class GitRepositoryInspector {
  constructor(private readonly requestedRoot: string) {}

  private async git(...args: string[]): Promise<string> {
    try {
      const { stdout } = await execFileAsync('git', ['-C', this.requestedRoot, ...args], {
        encoding: 'utf8',
        maxBuffer: 10 * 1024 * 1024,
      });
      return stdout.trim();
    } catch (error) {
      throw new RepositoryInspectionError(
        `Git inspection failed: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  async inspect(): Promise<RepositorySnapshot> {
    const root = resolve(await this.git('rev-parse', '--show-toplevel'));
    const [headRevision, branch, status, tracked] = await Promise.all([
      this.git('rev-parse', 'HEAD'),
      this.git('branch', '--show-current'),
      this.git('status', '--porcelain=v1'),
      this.git('ls-files', '-z'),
    ]);
    const paths = tracked.split('\0').filter((path) => path.length > 0 && !blockedNames.test(path));
    const files = await Promise.all(
      paths.map(async (path): Promise<RepositoryFile> => ({
        path,
        sizeBytes: (await stat(resolve(root, path))).size,
        kind: classify(path),
      })),
    );
    const instructions = paths.filter((path) => /(^|\/)AGENTS\.md$/.test(path)).sort();
    return { root, headRevision, branch, clean: status.length === 0, instructions, files };
  }

  async readTextFile(path: string, maxBytes = 64 * 1024): Promise<FileContent> {
    if (blockedNames.test(path)) throw new RepositoryInspectionError(`Sensitive path is not readable: ${path}`);
    const root = resolve(await this.git('rev-parse', '--show-toplevel'));
    const target = resolve(root, path);
    if (!withinRoot(root, target)) throw new RepositoryInspectionError(`Path escapes repository root: ${path}`);
    const metadata = await stat(target);
    if (metadata.size > maxBytes) {
      throw new RepositoryInspectionError(`File exceeds the ${maxBytes}-byte context limit: ${path}`);
    }
    const content = await readFile(target, 'utf8');
    if (content.includes('\0')) throw new RepositoryInspectionError(`Binary file is not admissible context: ${path}`);
    return { path, content, sizeBytes: Buffer.byteLength(content) };
  }
}
