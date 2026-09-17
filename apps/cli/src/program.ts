import { Command } from 'commander';
import { FRAMEWORK_NAME, FRAMEWORK_VERSION, healthReport } from '@v3/shared';

export function createProgram(write: (message: string) => void = console.log): Command {
  const program = new Command();
  program.name('harness').description(`${FRAMEWORK_NAME} engineering harness`).version(FRAMEWORK_VERSION);
  program
    .command('doctor')
    .description('Check the local runtime foundation')
    .action(() => write(JSON.stringify(healthReport('cli'))));
  const lifecycle = program.command('lifecycle').description('Understand and inspect the controlled delivery loop');
  lifecycle
    .command('explain')
    .description('Explain the delivery loop in plain language')
    .action(() =>
      write(
        JSON.stringify({
          summary: 'Build the change, test it, have a separate reviewer check it, repair problems, and test it again before calling it done.',
          repairLimit: 3,
          completionRule: 'Work closes only when current-revision checks pass and an independent reviewer approves it.',
        }),
      ),
    );
  lifecycle
    .command('status')
    .description('Explain a lifecycle state')
    .requiredOption('--state <state>', 'Lifecycle state')
    .action(({ state }: { state: string }) => {
      const explanations: Readonly<Record<string, string>> = {
        planned: 'The work is defined but has not started.',
        eligible: 'The work has everything needed to begin.',
        running: 'An implementation or repair is in progress.',
        verifying: 'Objective checks are running against the current version.',
        reviewing: 'A separate reviewer is examining the current version.',
        repair_required: 'A check or review found something that must be fixed.',
        accepted: 'The checks and independent review passed.',
        closed: 'The work is complete and its evidence is recorded.',
        blocked: 'The work cannot safely continue without a decision or a new plan.',
      };
      const explanation = explanations[state];
      if (explanation === undefined) throw new Error(`Unknown lifecycle state: ${state}`);
      write(JSON.stringify({ state, explanation }));
    });
  return program;
}
