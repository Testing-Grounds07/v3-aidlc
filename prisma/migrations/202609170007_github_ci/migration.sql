-- Milestone 6: GitHub pull-request identity; CI results use canonical EvidenceRecord rows.
CREATE TABLE "GitHubPullRequest" (
    "id" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "workPackageId" TEXT NOT NULL,
    "changeProposalId" TEXT NOT NULL,
    "repository" TEXT NOT NULL,
    "number" INTEGER NOT NULL,
    "url" TEXT NOT NULL,
    "baseBranch" TEXT NOT NULL,
    "headBranch" TEXT NOT NULL,
    "headRevision" TEXT NOT NULL,
    "state" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "GitHubPullRequest_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "GitHubPullRequest_changeProposalId_key" ON "GitHubPullRequest"("changeProposalId");
CREATE UNIQUE INDEX "GitHubPullRequest_repository_number_key" ON "GitHubPullRequest"("repository", "number");
CREATE INDEX "GitHubPullRequest_projectId_state_idx" ON "GitHubPullRequest"("projectId", "state");
CREATE INDEX "GitHubPullRequest_workPackageId_createdAt_idx" ON "GitHubPullRequest"("workPackageId", "createdAt");

ALTER TABLE "GitHubPullRequest" ADD CONSTRAINT "GitHubPullRequest_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "GitHubPullRequest" ADD CONSTRAINT "GitHubPullRequest_workPackageId_fkey" FOREIGN KEY ("workPackageId") REFERENCES "WorkPackage"("id") ON DELETE CASCADE ON UPDATE CASCADE;
