-- Migration: 000002_unified_heroes_source_mapping.down.sql
-- Description: Rollback unified heroes source mapping additions

DROP INDEX IF EXISTS idx_roles_hero_origin;
DROP INDEX IF EXISTS idx_roles_origin_source;

ALTER TABLE roles 
DROP COLUMN IF EXISTS external_hero_id,
DROP COLUMN IF EXISTS origin_source;
