CREATE TABLE "FoundationRecord" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "FoundationRecord_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "FoundationRecord_name_key" ON "FoundationRecord"("name");
