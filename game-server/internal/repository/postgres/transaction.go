package postgres

import (
	"context"
	"errors"
	"fmt"
	"math/rand"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

// DefaultMaxTxRetries is the maximum number of attempts for retryable transaction errors (e.g. serialization failure 40001).
const DefaultMaxTxRetries = 10

// IsRetryableTxError checks whether a database error is safe to retry (serialization failure or deadlock detected).
func IsRetryableTxError(err error) bool {
	if err == nil {
		return false
	}
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) {
		// 40001 = serialization_failure, 40P01 = deadlock_detected
		return pgErr.Code == "40001" || pgErr.Code == "40P01"
	}
	return false
}

// WithTx executes a unit of work inside an explicit database transaction.
// If fn returns an error, the transaction is automatically rolled back.
// If fn succeeds, the transaction is committed.
func WithTx(ctx context.Context, pool *pgxpool.Pool, opts pgx.TxOptions, fn func(tx pgx.Tx) error) error {
	tx, err := pool.BeginTx(ctx, opts)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}

	defer func() {
		// Rollback is a no-op if tx was already committed.
		_ = tx.Rollback(ctx)
	}()

	if err := fn(tx); err != nil {
		return err
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	return nil
}

// WithTxRetry executes a unit of work inside an explicit database transaction with automatic retry on serialization failures.
func WithTxRetry(ctx context.Context, pool *pgxpool.Pool, opts pgx.TxOptions, maxRetries int, fn func(tx pgx.Tx) error) error {
	if maxRetries <= 0 {
		maxRetries = DefaultMaxTxRetries
	}

	var lastErr error
	baseBackoff := 5 * time.Millisecond

	for attempt := 1; attempt <= maxRetries; attempt++ {
		err := WithTx(ctx, pool, opts, fn)
		if err == nil {
			return nil
		}

		lastErr = err
		if !IsRetryableTxError(err) {
			return err
		}

		// Calculate exponential backoff with full jitter to prevent stampedes
		jitter := time.Duration(rand.Int63n(int64(baseBackoff) + 1))
		sleepDuration := baseBackoff + jitter

		select {
		case <-ctx.Done():
			return fmt.Errorf("context cancelled during tx retry: %w (last err: %v)", ctx.Err(), lastErr)
		case <-time.After(sleepDuration):
			if baseBackoff < 200*time.Millisecond {
				baseBackoff *= 2
			}
		}
	}

	return fmt.Errorf("transaction failed after %d attempts: %w", maxRetries, lastErr)
}
