-- Migration: 000002_unified_heroes_source_mapping.up.sql
-- Description: Expand schema with origin_source tracking and external hero ID for Unified Heroes crosswalk

-- 1. Expand: add origin_source column with safe default for backward-compatibility with V1 clients
ALTER TABLE roles 
ADD COLUMN IF NOT EXISTS origin_source VARCHAR(32) NOT NULL DEFAULT 'CANONICAL_BASELINE',
ADD COLUMN IF NOT EXISTS external_hero_id VARCHAR(32) DEFAULT NULL;

-- 2. Create covering index for origin_source lookups
CREATE INDEX IF NOT EXISTS idx_roles_origin_source ON roles(origin_source);
CREATE INDEX IF NOT EXISTS idx_roles_hero_origin ON roles(hero_code, origin_source);

-- 3. Backfill: classify ReturnSaiyan custom heroes and donor heroes
UPDATE roles 
SET origin_source = 'RETURN_SAIYAN_CUSTOM'
WHERE hero_code IN ('10060', '10063', '10064');

UPDATE roles 
SET origin_source = 'GLOBAL_DONOR'
WHERE hero_code IN ('10081', '10082', '10083', '10084', '10085', '10062', '10065', '10066', '10067', '10068', '10069', '10070', '90038', '90037');
