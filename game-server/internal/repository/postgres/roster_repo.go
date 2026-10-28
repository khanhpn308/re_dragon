package postgres

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

// PostgresRosterRepository handles persistence for server-gated hero entitlements.
type PostgresRosterRepository struct {
	pool *pgxpool.Pool
}

func NewPostgresRosterRepository(pool *pgxpool.Pool) *PostgresRosterRepository {
	return &PostgresRosterRepository{pool: pool}
}

// GrantUnlock unlocks a server-gated hero for an account.
func (r *PostgresRosterRepository) GrantUnlock(ctx context.Context, accountID int64, heroID int32, source string) error {
	if source == "" {
		source = "SERVER_GRANT"
	}

	query := `
	INSERT INTO roster_unlocks (account_id, hero_id, unlocked_at, source)
	VALUES ($1, $2, NOW(), $3)
	ON CONFLICT (account_id, hero_id) DO NOTHING;`

	_, err := r.pool.Exec(ctx, query, accountID, heroID, source)
	if err != nil {
		return fmt.Errorf("failed to grant hero unlock: %w", err)
	}

	return nil
}

// RevokeUnlock removes entitlement for a hero.
func (r *PostgresRosterRepository) RevokeUnlock(ctx context.Context, accountID int64, heroID int32) error {
	query := `
	DELETE FROM roster_unlocks
	WHERE account_id = $1 AND hero_id = $2;`

	_, err := r.pool.Exec(ctx, query, accountID, heroID)
	if err != nil {
		return fmt.Errorf("failed to revoke hero unlock: %w", err)
	}

	return nil
}

// IsUnlocked checks if a server-gated hero is unlocked for the account.
func (r *PostgresRosterRepository) IsUnlocked(ctx context.Context, accountID int64, heroID int32) (bool, error) {
	query := `
	SELECT EXISTS (
		SELECT 1 FROM roster_unlocks
		WHERE account_id = $1 AND hero_id = $2
	);`

	var exists bool
	err := r.pool.QueryRow(ctx, query, accountID, heroID).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("failed to check hero unlock: %w", err)
	}

	return exists, nil
}

// GetUnlockedHeroes returns the list of unlocked hero IDs for an account.
func (r *PostgresRosterRepository) GetUnlockedHeroes(ctx context.Context, accountID int64) ([]int32, error) {
	query := `
	SELECT hero_id
	FROM roster_unlocks
	WHERE account_id = $1
	ORDER BY hero_id ASC;`

	rows, err := r.pool.Query(ctx, query, accountID)
	if err != nil {
		return nil, fmt.Errorf("failed to query unlocked heroes: %w", err)
	}
	defer rows.Close()

	var heroIDs []int32
	for rows.Next() {
		var id int32
		if err := rows.Scan(&id); err != nil {
			return nil, fmt.Errorf("failed to scan hero id: %w", err)
		}
		heroIDs = append(heroIDs, id)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows iteration error: %w", err)
	}

	return heroIDs, nil
}
