package postgres

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"returnsaiyan/gameserver/internal/session"
)

// PostgresAccountRepository implements session.Authenticator backed by PostgreSQL.
type PostgresAccountRepository struct {
	pool *pgxpool.Pool
}

func NewPostgresAccountRepository(pool *pgxpool.Pool) *PostgresAccountRepository {
	return &PostgresAccountRepository{pool: pool}
}

func hashPassword(password, salt string) string {
	h := sha256.New()
	h.Write([]byte(password + salt))
	return hex.EncodeToString(h.Sum(nil))
}

func generateSalt() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

// Authenticate checks user credentials against the PostgreSQL accounts table.
func (r *PostgresAccountRepository) Authenticate(ctx context.Context, username, password string) (*session.Account, error) {
	if username == "" || password == "" {
		return nil, session.ErrInvalidCredentials
	}

	query := `
	SELECT id, username, password_hash, salt, created_at
	FROM accounts
	WHERE username = $1 AND status = 'ACTIVE';`

	var acc session.Account
	err := r.pool.QueryRow(ctx, query, username).Scan(
		&acc.ID,
		&acc.Username,
		&acc.PasswordHash,
		&acc.Salt,
		&acc.CreatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, session.ErrInvalidCredentials
		}
		return nil, fmt.Errorf("database query error: %w", err)
	}

	expectedHash := hashPassword(password, acc.Salt)
	if expectedHash != acc.PasswordHash {
		return nil, session.ErrInvalidCredentials
	}

	return &acc, nil
}

// Register creates a new player account in PostgreSQL.
func (r *PostgresAccountRepository) Register(ctx context.Context, username, password string) (*session.Account, error) {
	if username == "" || password == "" {
		return nil, session.ErrEmptyCredentials
	}

	salt := generateSalt()
	passHash := hashPassword(password, salt)
	now := time.Now().UTC()

	query := `
	INSERT INTO accounts (username, password_hash, salt, status, created_at, updated_at)
	VALUES ($1, $2, $3, 'ACTIVE', $4, $4)
	RETURNING id, username, created_at;`

	var acc session.Account
	acc.PasswordHash = passHash
	acc.Salt = salt

	err := r.pool.QueryRow(ctx, query, username, passHash, salt, now).Scan(
		&acc.ID,
		&acc.Username,
		&acc.CreatedAt,
	)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" { // unique_violation
			return nil, session.ErrAccountExists
		}
		return nil, fmt.Errorf("failed to register account: %w", err)
	}

	// Create default starter character role for newly registered account
	queryRole := `
	INSERT INTO roles (account_id, name, hero_code, level, exp, gender, status, vip, guild, created_at, updated_at)
	VALUES ($1, $2, '10001', 1, 0, 1, 0, 0, '', NOW(), NOW())
	ON CONFLICT DO NOTHING;`
	_, _ = r.pool.Exec(ctx, queryRole, acc.ID, username)

	return &acc, nil
}

// GetRoles retrieves all roles owned by the account.
func (r *PostgresAccountRepository) GetRoles(ctx context.Context, accountID int64) ([]*session.Role, error) {
	query := `
	SELECT id, account_id, name, hero_code, level, exp, gender, status, vip, guild
	FROM roles
	WHERE account_id = $1
	ORDER BY id ASC;`

	rows, err := r.pool.Query(ctx, query, accountID)
	if err != nil {
		return nil, fmt.Errorf("failed to query roles: %w", err)
	}
	defer rows.Close()

	var roles []*session.Role
	for rows.Next() {
		var role session.Role
		var exp int64
		err := rows.Scan(
			&role.ID,
			&role.AccountID,
			&role.Name,
			&role.HeroCode,
			&role.Level,
			&exp,
			&role.Gender,
			&role.Status,
			&role.Vip,
			&role.Guild,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan role row: %w", err)
		}
		roles = append(roles, &role)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows iteration error: %w", err)
	}

	return roles, nil
}

// AddRole inserts a new character role for the account.
func (r *PostgresAccountRepository) AddRole(ctx context.Context, accountID int64, role *session.Role) error {
	query := `
	INSERT INTO roles (account_id, name, hero_code, level, exp, gender, status, vip, guild, created_at, updated_at)
	VALUES ($1, $2, $3, $4, 0, $5, $6, $7, $8, NOW(), NOW())
	RETURNING id;`

	err := r.pool.QueryRow(ctx, query,
		accountID,
		role.Name,
		role.HeroCode,
		role.Level,
		role.Gender,
		role.Status,
		role.Vip,
		role.Guild,
	).Scan(&role.ID)

	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return fmt.Errorf("character name %q already exists for this account", role.Name)
		}
		return fmt.Errorf("failed to insert role: %w", err)
	}

	role.AccountID = accountID
	return nil
}
