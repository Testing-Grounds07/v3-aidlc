import { PrismaClient } from './generated/client/index.js';

export function createDatabaseClient(): PrismaClient {
  return new PrismaClient();
}
