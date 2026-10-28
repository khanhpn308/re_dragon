-- Migration: 000001_init_schema.down.sql
-- Description: Rollback core schema in reverse dependency order

DROP TABLE IF EXISTS player_progression CASCADE;
DROP TABLE IF EXISTS player_inventories CASCADE;
DROP TABLE IF EXISTS roster_unlocks CASCADE;
DROP TABLE IF EXISTS roles CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS accounts CASCADE;

