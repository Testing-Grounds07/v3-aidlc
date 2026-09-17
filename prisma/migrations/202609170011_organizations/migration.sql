-- Milestone 11: organization, team, membership, project tenancy, and quotas.
CREATE TABLE "Organization" (
    "id" TEXT NOT NULL, "name" TEXT NOT NULL, "slug" TEXT NOT NULL, "status" TEXT NOT NULL DEFAULT 'active',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "Organization_pkey" PRIMARY KEY ("id")
);
CREATE TABLE "Team" (
    "id" TEXT NOT NULL, "organizationId" TEXT NOT NULL, "name" TEXT NOT NULL, "slug" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'active', "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL, CONSTRAINT "Team_pkey" PRIMARY KEY ("id")
);
CREATE TABLE "Membership" (
    "id" TEXT NOT NULL, "organizationId" TEXT NOT NULL, "teamId" TEXT, "principalId" TEXT NOT NULL,
    "organizationRole" TEXT NOT NULL, "teamRole" TEXT, "status" TEXT NOT NULL DEFAULT 'invited',
    "expiresAt" TIMESTAMP(3), "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL, CONSTRAINT "Membership_pkey" PRIMARY KEY ("id")
);
CREATE TABLE "OrganizationQuota" (
    "id" TEXT NOT NULL, "organizationId" TEXT NOT NULL, "dimension" TEXT NOT NULL,
    "maximum" DOUBLE PRECISION NOT NULL, "used" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "version" INTEGER NOT NULL DEFAULT 1, "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "OrganizationQuota_pkey" PRIMARY KEY ("id")
);
ALTER TABLE "Project" ADD COLUMN "organizationId" TEXT;
ALTER TABLE "Project" ADD COLUMN "teamId" TEXT;
CREATE UNIQUE INDEX "Organization_slug_key" ON "Organization"("slug");
CREATE UNIQUE INDEX "Team_organizationId_slug_key" ON "Team"("organizationId", "slug");
CREATE INDEX "Team_organizationId_status_idx" ON "Team"("organizationId", "status");
CREATE UNIQUE INDEX "Membership_organizationId_teamId_principalId_key" ON "Membership"("organizationId", "teamId", "principalId");
CREATE INDEX "Membership_principalId_status_idx" ON "Membership"("principalId", "status");
CREATE INDEX "Membership_organizationId_teamId_status_idx" ON "Membership"("organizationId", "teamId", "status");
CREATE UNIQUE INDEX "OrganizationQuota_organizationId_dimension_key" ON "OrganizationQuota"("organizationId", "dimension");
CREATE INDEX "Project_organizationId_teamId_idx" ON "Project"("organizationId", "teamId");
ALTER TABLE "Team" ADD CONSTRAINT "Team_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Membership" ADD CONSTRAINT "Membership_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Membership" ADD CONSTRAINT "Membership_teamId_fkey" FOREIGN KEY ("teamId") REFERENCES "Team"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "OrganizationQuota" ADD CONSTRAINT "OrganizationQuota_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Project" ADD CONSTRAINT "Project_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "Project" ADD CONSTRAINT "Project_teamId_fkey" FOREIGN KEY ("teamId") REFERENCES "Team"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
