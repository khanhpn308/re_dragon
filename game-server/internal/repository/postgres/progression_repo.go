package postgres

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PlayerProgression tracks campaign and story progression for a character.
type PlayerProgression struct {
	RoleID        int32     `json:"role_id"`
	StageID       int       `json:"stage_id"`
	StageProgress int       `json:"stage_progress"`
	Stars         int       `json:"stars"`
	UpdatedAt     time.Time `json:"updated_at"`
}

// PostgresProgressionRepository handles progression persistence.
type PostgresProgressionRepository struct {
	pool *pgxpool.Pool
}

func NewPostgresProgressionRepository(pool *pgxpool.Pool) *PostgresProgressionRepository {
	return &PostgresProgressionRepository{pool: pool}
}

// GetProgression retrieves progression for a role.
func (r *PostgresProgressionRepository) GetProgression(ctx context.Context, roleID int32) (*PlayerProgression, error) {
	query := `
	SELECT role_id, stage_id, stage_progress, stars, updated_at
	FROM player_progression
	WHERE role_id = $1;`

	var p PlayerProgression
	err := r.pool.QueryRow(ctx, query, roleID).Scan(
		&p.RoleID,
		&p.StageID,
		&p.StageProgress,
		&p.Stars,
		&p.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			// Return default progression for new character
			return &PlayerProgression{
				RoleID:        roleID,
				StageID:       1,
				StageProgress: 0,
				Stars:         0,
				UpdatedAt:     time.Now().UTC(),
			}, nil
		}
		return nil, fmt.Errorf("failed to query player progression: %w", err)
	}

	return &p, nil
}

// SaveProgression upserts progression record for a role.
func (r *PostgresProgressionRepository) SaveProgression(ctx context.Context, roleID int32, stageID, stageProgress, stars int) error {
	query := `
	INSERT INTO player_progression (role_id, stage_id, stage_progress, stars, updated_at)
	VALUES ($1, $2, $3, $4, NOW())
	ON CONFLICT (role_id) DO UPDATE SET
		stage_id = EXCLUDED.stage_id,
		stage_progress = EXCLUDED.stage_progress,
		stars = EXCLUDED.stars,
		updated_at = NOW();`

	_, err := r.pool.Exec(ctx, query, roleID, stageID, stageProgress, stars)
	if err != nil {
		return fmt.Errorf("failed to save player progression: %w", err)
	}

	return nil
}
