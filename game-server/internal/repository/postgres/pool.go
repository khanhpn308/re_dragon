package postgres

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// PoolConfig holds connection pool tuning parameters per DB-GAME standard.
type PoolConfig struct {
	DSN             string
	MaxConns        int32
	MinConns        int32
	MaxConnLifetime time.Duration
	MaxConnIdleTime time.Duration
	AcquireTimeout  time.Duration
}

// DefaultPoolConfig returns balanced settings for high-throughput concurrency.
func DefaultPoolConfig(dsn string) PoolConfig {
	return PoolConfig{
		DSN:             dsn,
		MaxConns:        50,
		MinConns:        5,
		MaxConnLifetime: 1 * time.Hour,
		MaxConnIdleTime: 15 * time.Minute,
		AcquireTimeout:  3 * time.Second,
	}
}

// NewPool initializes and validates a bounded pgxpool connection pool.
func NewPool(ctx context.Context, cfg PoolConfig) (*pgxpool.Pool, error) {
	poolCfg, err := pgxpool.ParseConfig(cfg.DSN)
	if err != nil {
		return nil, fmt.Errorf("failed to parse PostgreSQL DSN: %w", err)
	}

	if cfg.MaxConns <= 0 {
		cfg.MaxConns = 50
	}
	if cfg.MinConns <= 0 {
		cfg.MinConns = 5
	}
	if cfg.AcquireTimeout <= 0 {
		cfg.AcquireTimeout = 3 * time.Second
	}

	poolCfg.MaxConns = cfg.MaxConns
	poolCfg.MinConns = cfg.MinConns
	poolCfg.MaxConnLifetime = cfg.MaxConnLifetime
	poolCfg.MaxConnIdleTime = cfg.MaxConnIdleTime

	pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
	if err != nil {
		return nil, fmt.Errorf("failed to create pgxpool: %w", err)
	}

	pingCtx, cancel := context.WithTimeout(ctx, cfg.AcquireTimeout)
	defer cancel()

	if err := pool.Ping(pingCtx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("failed to ping PostgreSQL: %w", err)
	}

	return pool, nil
}
