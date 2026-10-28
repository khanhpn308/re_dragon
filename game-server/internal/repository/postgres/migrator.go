package postgres

import (
	"context"
	"embed"
	"fmt"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed sql_migrations/*.sql
var migrationFS embed.FS

const (
	MigrationAdvisoryLockID = 772284
)

// Migration represents a single versioned migration script.
type Migration struct {
	Version int
	Name    string
	UpSQL   string
	DownSQL string
}

// Migrator manages versioned database migrations.
type Migrator struct {
	pool *pgxpool.Pool
}

// NewMigrator creates a new Migrator.
func NewMigrator(pool *pgxpool.Pool) *Migrator {
	return &Migrator{pool: pool}
}

// loadMigrations parses embedded SQL files.
func loadMigrations() ([]Migration, error) {
	entries, err := migrationFS.ReadDir("sql_migrations")
	if err != nil {
		return nil, fmt.Errorf("failed to read embedded migrations directory: %w", err)
	}

	upFiles := make(map[int]string)
	downFiles := make(map[int]string)
	names := make(map[int]string)

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		filename := entry.Name()
		parts := strings.SplitN(filename, "_", 2)
		if len(parts) < 2 {
			continue
		}
		ver, err := strconv.Atoi(parts[0])
		if err != nil {
			continue
		}

		content, err := migrationFS.ReadFile(filepath.Join("sql_migrations", filename))
		if err != nil {
			return nil, fmt.Errorf("failed to read migration file %s: %w", filename, err)
		}

		if strings.HasSuffix(filename, ".up.sql") {
			upFiles[ver] = string(content)
			names[ver] = strings.TrimSuffix(parts[1], ".up.sql")
		} else if strings.HasSuffix(filename, ".down.sql") {
			downFiles[ver] = string(content)
		}
	}

	var versions []int
	for v := range upFiles {
		versions = append(versions, v)
	}
	sort.Ints(versions)

	var migrations []Migration
	for _, v := range versions {
		migrations = append(migrations, Migration{
			Version: v,
			Name:    names[v],
			UpSQL:   upFiles[v],
			DownSQL: downFiles[v],
		})
	}

	return migrations, nil
}

// Up applies all pending migrations in order.
func (m *Migrator) Up(ctx context.Context) error {
	migrations, err := loadMigrations()
	if err != nil {
		return err
	}

	conn, err := m.pool.Acquire(ctx)
	if err != nil {
		return fmt.Errorf("failed to acquire connection for migration: %w", err)
	}
	defer conn.Release()

	// Acquire advisory lock
	if _, err := conn.Exec(ctx, "SELECT pg_advisory_lock($1)", MigrationAdvisoryLockID); err != nil {
		return fmt.Errorf("failed to acquire migration advisory lock: %w", err)
	}
	defer func() {
		_, _ = conn.Exec(context.Background(), "SELECT pg_advisory_unlock($1)", MigrationAdvisoryLockID)
	}()

	// Ensure schema_migrations table exists
	createTableSQL := `
	CREATE TABLE IF NOT EXISTS schema_migrations (
		version INT PRIMARY KEY,
		name VARCHAR(128) NOT NULL,
		applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
	);`
	if _, err := conn.Exec(ctx, createTableSQL); err != nil {
		return fmt.Errorf("failed to ensure schema_migrations table: %w", err)
	}

	for _, mig := range migrations {
		var exists bool
		err := conn.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version = $1)", mig.Version).Scan(&exists)
		if err != nil {
			return fmt.Errorf("failed to check migration version %d: %w", mig.Version, err)
		}

		if exists {
			continue
		}

		tx, err := conn.Begin(ctx)
		if err != nil {
			return fmt.Errorf("failed to start migration transaction: %w", err)
		}

		if _, err := tx.Exec(ctx, mig.UpSQL); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("failed executing migration up %d (%s): %w", mig.Version, mig.Name, err)
		}

		if _, err := tx.Exec(ctx, "INSERT INTO schema_migrations (version, name, applied_at) VALUES ($1, $2, NOW())", mig.Version, mig.Name); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("failed recording migration version %d: %w", mig.Version, err)
		}

		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("failed committing migration %d: %w", mig.Version, err)
		}
	}

	return nil
}

// Down rolls back the latest applied migration.
func (m *Migrator) Down(ctx context.Context) error {
	migrations, err := loadMigrations()
	if err != nil {
		return err
	}

	conn, err := m.pool.Acquire(ctx)
	if err != nil {
		return fmt.Errorf("failed to acquire connection for rollback: %w", err)
	}
	defer conn.Release()

	if _, err := conn.Exec(ctx, "SELECT pg_advisory_lock($1)", MigrationAdvisoryLockID); err != nil {
		return fmt.Errorf("failed to acquire migration advisory lock: %w", err)
	}
	defer func() {
		_, _ = conn.Exec(context.Background(), "SELECT pg_advisory_unlock($1)", MigrationAdvisoryLockID)
	}()

	var latestVersion int
	err = conn.QueryRow(ctx, "SELECT COALESCE(MAX(version), 0) FROM schema_migrations").Scan(&latestVersion)
	if err != nil {
		return fmt.Errorf("failed querying latest migration version: %w", err)
	}

	if latestVersion == 0 {
		return nil // Nothing to rollback
	}

	var target *Migration
	for i := range migrations {
		if migrations[i].Version == latestVersion {
			target = &migrations[i]
			break
		}
	}

	if target == nil || target.DownSQL == "" {
		return fmt.Errorf("no down migration found for version %d", latestVersion)
	}

	tx, err := conn.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed starting rollback transaction: %w", err)
	}

	if _, err := tx.Exec(ctx, target.DownSQL); err != nil {
		_ = tx.Rollback(ctx)
		return fmt.Errorf("failed executing rollback down %d: %w", target.Version, err)
	}

	if _, err := tx.Exec(ctx, "DELETE FROM schema_migrations WHERE version = $1", target.Version); err != nil {
		_ = tx.Rollback(ctx)
		return fmt.Errorf("failed removing migration record %d: %w", target.Version, err)
	}

	return tx.Commit(ctx)
}

// CurrentVersion returns the latest applied migration version.
func (m *Migrator) CurrentVersion(ctx context.Context) (int, error) {
	conn, err := m.pool.Acquire(ctx)
	if err != nil {
		return 0, err
	}
	defer conn.Release()

	var exists bool
	_ = conn.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'schema_migrations')").Scan(&exists)
	if !exists {
		return 0, nil
	}

	var ver int
	err = conn.QueryRow(ctx, "SELECT COALESCE(MAX(version), 0) FROM schema_migrations").Scan(&ver)
	return ver, err
}
