-- Milestone 7: human decisions and revocable standing delegations.
CREATE TABLE "DecisionRequest" (
    "id" TEXT NOT NULL, "projectId" TEXT NOT NULL, "actionId" TEXT NOT NULL,
    "headline" TEXT NOT NULL, "explanation" TEXT NOT NULL, "impact" TEXT NOT NULL,
    "actionNeeded" TEXT NOT NULL, "question" TEXT NOT NULL, "options" JSONB NOT NULL,
    "recommendedOptionId" TEXT, "unaffectedWork" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending', "requestedAt" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "DecisionRequest_pkey" PRIMARY KEY ("id")
);
CREATE TABLE "HumanDecision" (
    "id" TEXT NOT NULL, "projectId" TEXT NOT NULL, "decisionRequestId" TEXT NOT NULL,
    "selectedOptionId" TEXT NOT NULL, "userWords" TEXT NOT NULL,
    "submittedAt" TIMESTAMP(3) NOT NULL, "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "HumanDecision_pkey" PRIMARY KEY ("id")
);
CREATE TABLE "StandingDelegation" (
    "id" TEXT NOT NULL, "projectId" TEXT NOT NULL, "grantedBy" TEXT NOT NULL,
    "actionTypes" TEXT[], "targets" TEXT[], "requiredEvidence" TEXT[],
    "policyVersion" TEXT NOT NULL, "userWords" TEXT NOT NULL, "grantedAt" TIMESTAMP(3) NOT NULL,
    "expiresAt" TIMESTAMP(3), "revokedAt" TIMESTAMP(3), "revocationWords" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "StandingDelegation_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "DecisionRequest_projectId_status_requestedAt_idx" ON "DecisionRequest"("projectId", "status", "requestedAt");
CREATE UNIQUE INDEX "HumanDecision_decisionRequestId_key" ON "HumanDecision"("decisionRequestId");
CREATE INDEX "HumanDecision_projectId_submittedAt_idx" ON "HumanDecision"("projectId", "submittedAt");
CREATE INDEX "StandingDelegation_projectId_revokedAt_expiresAt_idx" ON "StandingDelegation"("projectId", "revokedAt", "expiresAt");
ALTER TABLE "DecisionRequest" ADD CONSTRAINT "DecisionRequest_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "HumanDecision" ADD CONSTRAINT "HumanDecision_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "HumanDecision" ADD CONSTRAINT "HumanDecision_decisionRequestId_fkey" FOREIGN KEY ("decisionRequestId") REFERENCES "DecisionRequest"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "StandingDelegation" ADD CONSTRAINT "StandingDelegation_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
