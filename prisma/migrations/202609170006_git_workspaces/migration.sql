-- Milestone 5: isolated Git worktrees and review-ready change proposals.
CREATE TABLE "WorktreeSession" (
    "id" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "workPackageId" TEXT NOT NULL,
    "repositoryRoot" TEXT NOT NULL,
    "worktreePath" TEXT NOT NULL,
    "branch" TEXT NOT NULL,
    "baseRevision" TEXT NOT NULL,
    "headRevision" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'active',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "WorktreeSession_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "ChangeProposal" (
    "id" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "workPackageId" TEXT NOT NULL,
    "worktreeSessionId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "body" TEXT NOT NULL,
    "baseRevision" TEXT NOT NULL,
    "headRevision" TEXT NOT NULL,
    "branch" TEXT NOT NULL,
    "changedFiles" TEXT[],
    "verificationEvidenceIds" TEXT[],
    "digest" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'prepared',
    "externalUrl" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "ChangeProposal_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "WorktreeSession_projectId_branch_key" ON "WorktreeSession"("projectId", "branch");
CREATE UNIQUE INDEX "WorktreeSession_projectId_worktreePath_key" ON "WorktreeSession"("projectId", "worktreePath");
CREATE INDEX "WorktreeSession_workPackageId_status_idx" ON "WorktreeSession"("workPackageId", "status");
CREATE INDEX "ChangeProposal_projectId_status_idx" ON "ChangeProposal"("projectId", "status");
CREATE INDEX "ChangeProposal_workPackageId_createdAt_idx" ON "ChangeProposal"("workPackageId", "createdAt");
CREATE UNIQUE INDEX "ChangeProposal_worktreeSessionId_headRevision_key" ON "ChangeProposal"("worktreeSessionId", "headRevision");

ALTER TABLE "WorktreeSession" ADD CONSTRAINT "WorktreeSession_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "WorktreeSession" ADD CONSTRAINT "WorktreeSession_workPackageId_fkey" FOREIGN KEY ("workPackageId") REFERENCES "WorkPackage"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ChangeProposal" ADD CONSTRAINT "ChangeProposal_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ChangeProposal" ADD CONSTRAINT "ChangeProposal_workPackageId_fkey" FOREIGN KEY ("workPackageId") REFERENCES "WorkPackage"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ChangeProposal" ADD CONSTRAINT "ChangeProposal_worktreeSessionId_fkey" FOREIGN KEY ("worktreeSessionId") REFERENCES "WorktreeSession"("id") ON DELETE CASCADE ON UPDATE CASCADE;
