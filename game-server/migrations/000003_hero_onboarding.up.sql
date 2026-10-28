-- P3b additive schema: owned heroes are not login roles or donor entitlements.
CREATE TABLE IF NOT EXISTS hero_instances (
 id BIGSERIAL PRIMARY KEY,
 account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 hero_code INTEGER NOT NULL,
 aptitude INTEGER NOT NULL DEFAULT 0 CHECK(aptitude >= 0),
 level SMALLINT NOT NULL DEFAULT 1 CHECK(level BETWEEN 1 AND 200),
 promotion_tier SMALLINT NOT NULL DEFAULT 0 CHECK(promotion_tier BETWEEN 0 AND 40),
 combat_power BIGINT CHECK(combat_power IS NULL OR combat_power >= 0),
 acquired_via VARCHAR(32) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(account_id,id)
);
CREATE INDEX IF NOT EXISTS idx_hero_instances_account ON hero_instances(account_id);
CREATE TABLE IF NOT EXISTS hero_summon_operations (
 account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 request_id VARCHAR(128) NOT NULL,
 mode VARCHAR(32) NOT NULL CHECK(mode='EARTH_X1'),
 hero_code INTEGER NOT NULL,
 hero_instance_id BIGINT,
 currency_debited BIGINT NOT NULL DEFAULT 0 CHECK(currency_debited >= 0),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(account_id,request_id),
 FOREIGN KEY(account_id,hero_instance_id) REFERENCES hero_instances(account_id,id)
);
CREATE TABLE IF NOT EXISTS hero_formations (
 account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 slot SMALLINT NOT NULL CHECK(slot BETWEEN 1 AND 4),
 hero_instance_id BIGINT NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(account_id,slot),
 UNIQUE(account_id,hero_instance_id),
 FOREIGN KEY(account_id,hero_instance_id)
 REFERENCES hero_instances(account_id,id) ON DELETE CASCADE
);
