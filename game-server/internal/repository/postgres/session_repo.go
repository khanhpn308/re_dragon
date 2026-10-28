package postgres

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"returnsaiyan/gameserver/internal/session"
)

// SessionRecord represents the persistent state of a session in PostgreSQL.
type SessionRecord struct {
	Token          string
	AccountID      int64
	ConnID         string
	State          string
	SelectedRoleID *int32
	ExpiresAt      time.Time
	CreatedAt      time.Time
	LastActiveAt   time.Time
}

// PostgresSessionRepository handles persistence for player sessions.
type PostgresSessionRepository struct {
	pool *pgxpool.Pool
}

func NewPostgresSessionRepository(pool *pgxpool.Pool) *PostgresSessionRepository {
	return &PostgresSessionRepository{pool: pool}
}

// SaveSession inserts or updates an active session in the database.
func (r *PostgresSessionRepository) SaveSession(ctx context.Context, sess *session.Session) error {
	if sess == nil {
		return errors.New("cannot save nil session")
	}

	acc := sess.Account()
	if acc == nil {
		return errors.New("cannot save session without associated account")
	}

	var selectedRoleID *int32
	if r := sess.SelectedRole(); r != nil {
		selectedRoleID = &r.ID
	}

	query := `
	INSERT INTO sessions (
		token, account_id, conn_id, state, selected_role_id, expires_at, created_at, last_active_at
	) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	ON CONFLICT (token) DO UPDATE SET
		conn_id = EXCLUDED.conn_id,
		state = EXCLUDED.state,
		selected_role_id = EXCLUDED.selected_role_id,
		expires_at = EXCLUDED.expires_at,
		last_active_at = EXCLUDED.last_active_at;`

	now := time.Now().UTC()
	// Default expires 24h if zero
	expiresAt := now.Add(24 * time.Hour)

	_, err := r.pool.Exec(ctx, query,
		sess.Token(),
		acc.ID,
		sess.ConnID(),
		sess.State().String(),
		selectedRoleID,
		expiresAt,
		now,
		now,
	)
	if err != nil {
		return fmt.Errorf("failed to save session: %w", err)
	}

	return nil
}

// GetSession retrieves the session record by its token.
func (r *PostgresSessionRepository) GetSession(ctx context.Context, token string) (*SessionRecord, error) {
	query := `
	SELECT token, account_id, conn_id, state, selected_role_id, expires_at, created_at, last_active_at
	FROM sessions
	WHERE token = $1;`

	var rec SessionRecord
	var selectedRoleID sql.NullInt32

	err := r.pool.QueryRow(ctx, query, token).Scan(
		&rec.Token,
		&rec.AccountID,
		&rec.ConnID,
		&rec.State,
		&selectedRoleID,
		&rec.ExpiresAt,
		&rec.CreatedAt,
		&rec.LastActiveAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, session.ErrSessionNotFound
		}
		return nil, fmt.Errorf("failed to get session: %w", err)
	}

	if selectedRoleID.Valid {
		val := selectedRoleID.Int32
		rec.SelectedRoleID = &val
	}

	return &rec, nil
}

// UpdateSessionState updates state and activity time.
func (r *PostgresSessionRepository) UpdateSessionState(ctx context.Context, token string, state session.SessionState, lastActive time.Time) error {
	query := `
	UPDATE sessions
	SET state = $1, last_active_at = $2
	WHERE token = $3;`

	tag, err := r.pool.Exec(ctx, query, state.String(), lastActive, token)
	if err != nil {
		return fmt.Errorf("failed to update session state: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return session.ErrSessionNotFound
	}

	return nil
}

// UpdateSelectedRole updates the active role for the session.
func (r *PostgresSessionRepository) UpdateSelectedRole(ctx context.Context, token string, roleID int32) error {
	query := `
	UPDATE sessions
	SET selected_role_id = $1, last_active_at = NOW()
	WHERE token = $2;`

	tag, err := r.pool.Exec(ctx, query, roleID, token)
	if err != nil {
		return fmt.Errorf("failed to update session role: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return session.ErrSessionNotFound
	}

	return nil
}

// EvictSession marks a specific session as EVICTED.
func (r *PostgresSessionRepository) EvictSession(ctx context.Context, token string) error {
	query := `
	UPDATE sessions
	SET state = 'EVICTED', last_active_at = NOW()
	WHERE token = $1;`

	tag, err := r.pool.Exec(ctx, query, token)
	if err != nil {
		return fmt.Errorf("failed to evict session: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return session.ErrSessionNotFound
	}

	return nil
}

// EvictAccountSessions marks all active sessions for an account as EVICTED, except for excludeToken.
func (r *PostgresSessionRepository) EvictAccountSessions(ctx context.Context, accountID int64, excludeToken string) (int64, error) {
	query := `
	UPDATE sessions
	SET state = 'EVICTED', last_active_at = NOW()
	WHERE account_id = $1 AND token != $2 AND state NOT IN ('EVICTED', 'EXPIRED');`

	tag, err := r.pool.Exec(ctx, query, accountID, excludeToken)
	if err != nil {
		return 0, fmt.Errorf("failed to evict account sessions: %w", err)
	}

	return tag.RowsAffected(), nil
}

// DeleteExpiredSessions cleans up expired sessions.
func (r *PostgresSessionRepository) DeleteExpiredSessions(ctx context.Context, cutoff time.Time) (int64, error) {
	query := `
	DELETE FROM sessions
	WHERE expires_at < $1;`

	tag, err := r.pool.Exec(ctx, query, cutoff)
	if err != nil {
		return 0, fmt.Errorf("failed to delete expired sessions: %w", err)
	}

	return tag.RowsAffected(), nil
}
