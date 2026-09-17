CREATE TABLE "RepositoryRegistration" (
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "rootPath" TEXT NOT NULL,
  "defaultBranch" TEXT NOT NULL,
  "headRevision" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "RepositoryRegistration_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Investigation" (
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "repositoryId" TEXT NOT NULL,
  "task" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "artifactPath" TEXT NOT NULL,
  "digest" TEXT NOT NULL,
  "manifest" JSONB NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Investigation_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "RepositoryRegistration_projectId_rootPath_key" ON "RepositoryRegistration"("projectId", "rootPath");
CREATE INDEX "RepositoryRegistration_projectId_idx" ON "RepositoryRegistration"("projectId");
CREATE INDEX "Investigation_projectId_createdAt_idx" ON "Investigation"("projectId", "createdAt");
CREATE INDEX "Investigation_repositoryId_createdAt_idx" ON "Investigation"("repositoryId", "createdAt");

ALTER TABLE "RepositoryRegistration" ADD CONSTRAINT "RepositoryRegistration_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Investigation" ADD CONSTRAINT "Investigation_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Investigation" ADD CONSTRAINT "Investigation_repositoryId_fkey" FOREIGN KEY ("repositoryId") REFERENCES "RepositoryRegistration"("id") ON DELETE CASCADE ON UPDATE CASCADE;
