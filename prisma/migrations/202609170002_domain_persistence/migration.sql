CREATE TYPE "ProjectStatus" AS ENUM ('ACTIVE', 'PAUSED', 'COMPLETED', 'CANCELLED');
CREATE TYPE "RequirementStatus" AS ENUM ('DRAFT', 'APPROVED', 'SUPERSEDED');
CREATE TYPE "PlanStatus" AS ENUM ('DRAFT', 'APPROVED', 'SUPERSEDED');
CREATE TYPE "WorkPackageStatus" AS ENUM (
  'PROPOSED', 'PLANNED', 'ELIGIBLE', 'LEASED', 'RUNNING', 'EVIDENCE_PENDING',
  'VERIFYING', 'REVIEWING', 'REPAIR_REQUIRED', 'REPLAN_REQUIRED',
  'DECISION_REQUIRED', 'BLOCKED', 'ACCEPTED', 'CLOSED', 'CANCELLED', 'SUPERSEDED'
);

CREATE TABLE "Project" (
  "id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT NOT NULL,
  "status" "ProjectStatus" NOT NULL DEFAULT 'ACTIVE',
  "version" INTEGER NOT NULL DEFAULT 1,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Project_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Requirement" (
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "description" TEXT NOT NULL,
  "status" "RequirementStatus" NOT NULL DEFAULT 'DRAFT',
  "version" INTEGER NOT NULL DEFAULT 1,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Requirement_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "AcceptanceCriterion" (
  "id" TEXT NOT NULL,
  "requirementId" TEXT NOT NULL,
  "statement" TEXT NOT NULL,
  "verificationMethod" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "AcceptanceCriterion_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Plan" (
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "objective" TEXT NOT NULL,
  "status" "PlanStatus" NOT NULL DEFAULT 'DRAFT',
  "version" INTEGER NOT NULL DEFAULT 1,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Plan_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "WorkPackage" (
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "planId" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "objective" TEXT NOT NULL,
  "status" "WorkPackageStatus" NOT NULL DEFAULT 'PROPOSED',
  "version" INTEGER NOT NULL DEFAULT 1,
  "intentIds" TEXT[],
  "routeInstanceId" TEXT,
  "workstreamId" TEXT,
  "unitId" TEXT,
  "boltId" TEXT,
  "stage" TEXT NOT NULL,
  "modeId" TEXT,
  "posture" TEXT NOT NULL,
  "riskProfileId" TEXT,
  "expectedOutcomeTypes" TEXT[],
  "promotionTarget" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "WorkPackage_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "LifecycleEvent" (
  "sequence" BIGSERIAL NOT NULL,
  "id" TEXT NOT NULL,
  "projectId" TEXT NOT NULL,
  "type" TEXT NOT NULL,
  "aggregateType" TEXT NOT NULL,
  "aggregateId" TEXT NOT NULL,
  "aggregateVersion" INTEGER NOT NULL,
  "payload" JSONB NOT NULL,
  "occurredAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "LifecycleEvent_pkey" PRIMARY KEY ("sequence")
);

CREATE INDEX "Requirement_projectId_idx" ON "Requirement"("projectId");
CREATE INDEX "AcceptanceCriterion_requirementId_idx" ON "AcceptanceCriterion"("requirementId");
CREATE INDEX "Plan_projectId_idx" ON "Plan"("projectId");
CREATE INDEX "WorkPackage_projectId_idx" ON "WorkPackage"("projectId");
CREATE INDEX "WorkPackage_planId_idx" ON "WorkPackage"("planId");
CREATE INDEX "WorkPackage_status_idx" ON "WorkPackage"("status");
CREATE UNIQUE INDEX "LifecycleEvent_id_key" ON "LifecycleEvent"("id");
CREATE UNIQUE INDEX "LifecycleEvent_aggregateType_aggregateId_aggregateVersion_key" ON "LifecycleEvent"("aggregateType", "aggregateId", "aggregateVersion");
CREATE INDEX "LifecycleEvent_projectId_sequence_idx" ON "LifecycleEvent"("projectId", "sequence");
CREATE INDEX "LifecycleEvent_aggregateType_aggregateId_idx" ON "LifecycleEvent"("aggregateType", "aggregateId");

ALTER TABLE "Requirement" ADD CONSTRAINT "Requirement_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "AcceptanceCriterion" ADD CONSTRAINT "AcceptanceCriterion_requirementId_fkey" FOREIGN KEY ("requirementId") REFERENCES "Requirement"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Plan" ADD CONSTRAINT "Plan_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "WorkPackage" ADD CONSTRAINT "WorkPackage_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "WorkPackage" ADD CONSTRAINT "WorkPackage_planId_fkey" FOREIGN KEY ("planId") REFERENCES "Plan"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "LifecycleEvent" ADD CONSTRAINT "LifecycleEvent_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;
