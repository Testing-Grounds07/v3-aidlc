-- Milestone 9: segmented, sample-aware process health reports.
CREATE TABLE "ProcessHealthReport" (
    "id" TEXT NOT NULL, "projectId" TEXT NOT NULL,
    "windowStart" TIMESTAMP(3) NOT NULL, "windowEnd" TIMESTAMP(3) NOT NULL,
    "dimensions" JSONB NOT NULL, "metrics" JSONB NOT NULL, "recommendations" TEXT[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ProcessHealthReport_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "ProcessHealthReport_projectId_windowEnd_idx" ON "ProcessHealthReport"("projectId", "windowEnd");
CREATE UNIQUE INDEX "ProcessHealthReport_projectId_windowStart_windowEnd_id_key" ON "ProcessHealthReport"("projectId", "windowStart", "windowEnd", "id");
ALTER TABLE "ProcessHealthReport" ADD CONSTRAINT "ProcessHealthReport_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
