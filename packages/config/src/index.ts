import { z } from 'zod';

const environmentSchema = z.object({
  DATABASE_URL: z.string().min(1),
  V3_API_PORT: z.coerce.number().int().min(1).max(65535).default(4100),
});

export type RuntimeEnvironment = z.infer<typeof environmentSchema>;

export function readEnvironment(source: NodeJS.ProcessEnv = process.env): RuntimeEnvironment {
  return environmentSchema.parse(source);
}
