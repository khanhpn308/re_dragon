-- Migration: 000001_init_schema.up.sql
-- Description: Core schema for ReturnSaiyan Go Game Server (Accounts, Sessions, Roles, Roster Unlocks, Inventories, Progression)

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INT PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Accounts table: player credentials and status
CREATE TABLE IF NOT EXISTS accounts (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    salt VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Active player sessions table
CREATE TABLE IF NOT EXISTS sessions (
    token VARCHAR(64) PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    conn_id VARCHAR(64) NOT NULL DEFAULT '',
    state VARCHAR(32) NOT NULL DEFAULT 'AUTHENTICATED',
    selected_role_id INT DEFAULT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Character / Role instances
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL,
    hero_code VARCHAR(32) NOT NULL,
    level SMALLINT NOT NULL DEFAULT 1,
    exp BIGINT NOT NULL DEFAULT 0,
    gender SMALLINT NOT NULL DEFAULT 1,
    status SMALLINT NOT NULL DEFAULT 0,
    vip SMALLINT NOT NULL DEFAULT 0,
    guild VARCHAR(64) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_account_role_name UNIQUE (account_id, name)
);

-- Server-gated hero entitlements (for the 14 donor additions from Global)
CREATE TABLE IF NOT EXISTS roster_unlocks (
    account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    hero_id INT NOT NULL,
    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source VARCHAR(64) NOT NULL DEFAULT 'SERVER_GRANT',
    PRIMARY KEY (account_id, hero_id)
);

-- Player inventory slot items
CREATE TABLE IF NOT EXISTS player_inventories (
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    slot INT NOT NULL,
    item_id INT NOT NULL,
    count INT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (role_id, slot),
    CONSTRAINT chk_positive_count CHECK (count > 0)
);

-- Player campaign and world progression
CREATE TABLE IF NOT EXISTS player_progression (
    role_id INT PRIMARY KEY REFERENCES roles(id) ON DELETE CASCADE,
    stage_id INT NOT NULL DEFAULT 1,
    stage_progress INT NOT NULL DEFAULT 0,
    stars INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for high-throughput 5,000 CCU lookups
CREATE INDEX IF NOT EXISTS idx_accounts_username ON accounts(username);
CREATE INDEX IF NOT EXISTS idx_sessions_account_id ON sessions(account_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_roles_account_id ON roles(account_id);
CREATE INDEX IF NOT EXISTS idx_player_inventories_role_id ON player_inventories(role_id);
