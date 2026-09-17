CREATE TABLE "AgentRun" (
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "workPackageId" TEXT NOT NULL,
  "adapterId" TEXT NOT NULL,
  "profileId" TEXT NOT NULL,
  "requestDigest" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "summary" TEXT NOT NULL,
  "artifactIds" TEXT[],
  "evidenceIds" TEXT[],
  "findingIds" TEXT[],
  "satisfiedCriteria" TEXT[],
  "usage" JSONB NOT NULL,
  "providerResultRef" TEXT NOT NULL,
  "startedAt" TIMESTAMP(3) NOT NULL,
  "finishedAt" TIMESTAMP(3) NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "AgentRun_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "AgentRun_projectId_createdAt_idx" ON "AgentRun"("projectId", "createdAt");
CREATE INDEX "AgentRun_workPackageId_createdAt_idx" ON "AgentRun"("workPackageId", "createdAt");
CREATE INDEX "AgentRun_adapterId_status_idx" ON "AgentRun"("adapterId", "status");

ALTER TABLE "AgentRun" ADD CONSTRAINT "AgentRun_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "AgentRun" ADD CONSTRAINT "AgentRun_workPackageId_fkey" FOREIGN KEY ("workPackageId") REFERENCES "WorkPackage"("id") ON DELETE CASCADE ON UPDATE CASCADE;
