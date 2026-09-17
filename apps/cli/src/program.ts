import { Command } from 'commander';
import { FRAMEWORK_NAME, FRAMEWORK_VERSION, healthReport } from '@v3/shared';

export function createProgram(write: (message: string) => void = console.log): Command {
  const program = new Command();
  program.name('harness').description(`${FRAMEWORK_NAME} engineering harness`).version(FRAMEWORK_VERSION);
  program
    .command('doctor')
    .description('Check the local runtime foundation')
    .action(() => write(JSON.stringify(healthReport('cli'))));
  return program;
}
