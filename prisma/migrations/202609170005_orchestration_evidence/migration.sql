-- Milestone 4: durable verification evidence and gate decisions.
CREATE TABLE "EvidenceRecord" (
    "id" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "workPackageId" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "subjectRevision" TEXT NOT NULL,
    "producerId" TEXT NOT NULL,
    "producerRole" TEXT NOT NULL,
    "producerIndependenceGroup" TEXT NOT NULL,
    "collectedAt" TIMESTAMP(3) NOT NULL,
    "locator" TEXT NOT NULL,
    "sha256" TEXT NOT NULL,
    "assertions" TEXT[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "EvidenceRecord_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "GateDecision" (
    "id" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "workPackageId" TEXT NOT NULL,
    "revision" TEXT NOT NULL,
    "attempt" INTEGER NOT NULL,
    "outcome" TEXT NOT NULL,
    "promotable" BOOLEAN NOT NULL,
    "reasons" TEXT[],
    "evidenceIds" TEXT[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "GateDecision_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "EvidenceRecord_projectId_createdAt_idx" ON "EvidenceRecord"("projectId", "createdAt");
CREATE INDEX "EvidenceRecord_workPackageId_subjectRevision_idx" ON "EvidenceRecord"("workPackageId", "subjectRevision");
CREATE INDEX "EvidenceRecord_sha256_idx" ON "EvidenceRecord"("sha256");
CREATE UNIQUE INDEX "GateDecision_workPackageId_revision_attempt_key" ON "GateDecision"("workPackageId", "revision", "attempt");
CREATE INDEX "GateDecision_projectId_createdAt_idx" ON "GateDecision"("projectId", "createdAt");

ALTER TABLE "EvidenceRecord" ADD CONSTRAINT "EvidenceRecord_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "EvidenceRecord" ADD CONSTRAINT "EvidenceRecord_workPackageId_fkey" FOREIGN KEY ("workPackageId") REFERENCES "WorkPackage"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "GateDecision" ADD CONSTRAINT "GateDecision_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "GateDecision" ADD CONSTRAINT "GateDecision_workPackageId_fkey" FOREIGN KEY ("workPackageId") REFERENCES "WorkPackage"("id") ON DELETE CASCADE ON UPDATE CASCADE;
