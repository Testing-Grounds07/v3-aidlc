-- Milestone 10: independent evaluation results and comparable provider benchmarks.
CREATE TABLE "EvaluationResult" (
    "id" TEXT NOT NULL, "projectId" TEXT NOT NULL, "candidateId" TEXT NOT NULL,
    "caseId" TEXT NOT NULL, "caseVersion" TEXT NOT NULL, "contextRevision" TEXT NOT NULL,
    "profileId" TEXT NOT NULL, "evaluatorId" TEXT NOT NULL, "evaluatorIndependenceGroup" TEXT NOT NULL,
    "scores" JSONB NOT NULL, "weightedScore" DOUBLE PRECISION NOT NULL, "passed" BOOLEAN NOT NULL,
    "failures" TEXT[], "digest" TEXT NOT NULL, "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "EvaluationResult_pkey" PRIMARY KEY ("id")
);
CREATE TABLE "ProviderBenchmark" (
    "id" TEXT NOT NULL, "projectId" TEXT NOT NULL, "profileId" TEXT NOT NULL, "taskKind" TEXT NOT NULL,
    "sampleSize" INTEGER NOT NULL, "passRate" DOUBLE PRECISION NOT NULL, "meanScore" DOUBLE PRECISION NOT NULL,
    "medianLatencyMs" DOUBLE PRECISION NOT NULL, "meanCostMicros" DOUBLE PRECISION NOT NULL,
    "measuredAt" TIMESTAMP(3) NOT NULL, "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ProviderBenchmark_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "EvaluationResult_projectId_createdAt_idx" ON "EvaluationResult"("projectId", "createdAt");
CREATE INDEX "EvaluationResult_profileId_caseId_passed_idx" ON "EvaluationResult"("profileId", "caseId", "passed");
CREATE UNIQUE INDEX "EvaluationResult_candidateId_evaluatorId_key" ON "EvaluationResult"("candidateId", "evaluatorId");
CREATE INDEX "ProviderBenchmark_projectId_taskKind_measuredAt_idx" ON "ProviderBenchmark"("projectId", "taskKind", "measuredAt");
CREATE INDEX "ProviderBenchmark_profileId_taskKind_measuredAt_idx" ON "ProviderBenchmark"("profileId", "taskKind", "measuredAt");
ALTER TABLE "EvaluationResult" ADD CONSTRAINT "EvaluationResult_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ProviderBenchmark" ADD CONSTRAINT "ProviderBenchmark_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
