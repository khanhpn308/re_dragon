package postgres_test

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"returnsaiyan/gameserver/internal/repository/postgres"
	"returnsaiyan/gameserver/internal/session"
)

const testDSN = "postgres://returnsaiyan:returnsaiyan_pass@127.0.0.1:5432/returnsaiyan_dev?sslmode=disable"

func setupTestDB(t *testing.T) *postgres.Migrator {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	cfg := postgres.DefaultPoolConfig(testDSN)
	pool, err := postgres.NewPool(ctx, cfg)
	require.NoError(t, err, "failed to connect to test PostgreSQL database")
	t.Cleanup(func() {
		pool.Close()
	})

	migrator := postgres.NewMigrator(pool)
	// Apply all migrations
	err = migrator.Up(ctx)
	require.NoError(t, err, "failed to apply migrations")

	return migrator
}

func getTestPool(t *testing.T) *postgres.PoolConfig {
	cfg := postgres.DefaultPoolConfig(testDSN)
	return &cfg
}

func TestMigrator_Lifecycle(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	cfg := postgres.DefaultPoolConfig(testDSN)
	pool, err := postgres.NewPool(ctx, cfg)
	require.NoError(t, err)
	defer pool.Close()

	migrator := postgres.NewMigrator(pool)

	// 1. Initial Up (through additive version 3)
	err = migrator.Up(ctx)
	require.NoError(t, err)

	ver, err := migrator.CurrentVersion(ctx)
	require.NoError(t, err)
	assert.Equal(t, 3, ver)

	// 2. Idempotent Up
	err = migrator.Up(ctx)
	require.NoError(t, err)
	ver, err = migrator.CurrentVersion(ctx)
	require.NoError(t, err)
	assert.Equal(t, 3, ver)

	// 3. Down (Rollback version 3 -> version 2)
	err = migrator.Down(ctx)
	require.NoError(t, err)
	ver, err = migrator.CurrentVersion(ctx)
	require.NoError(t, err)
	assert.Equal(t, 2, ver)

	// 4. Down (Rollback version 2 -> version 1)
	err = migrator.Down(ctx)
	require.NoError(t, err)
	ver, err = migrator.CurrentVersion(ctx)
	require.NoError(t, err)
	assert.Equal(t, 1, ver)

	// 5. Down to version 0, then restore to latest version 3
	err = migrator.Down(ctx)
	require.NoError(t, err)
	ver, err = migrator.CurrentVersion(ctx)
	require.NoError(t, err)
	assert.Equal(t, 0, ver)

	err = migrator.Up(ctx)
	require.NoError(t, err)
	ver, err = migrator.CurrentVersion(ctx)
	require.NoError(t, err)
	assert.Equal(t, 3, ver)
}

func TestAccountRepository(t *testing.T) {
	setupTestDB(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := postgres.NewPool(ctx, postgres.DefaultPoolConfig(testDSN))
	require.NoError(t, err)
	defer pool.Close()

	repo := postgres.NewPostgresAccountRepository(pool)

	username := fmt.Sprintf("saiyan_%d", time.Now().UnixNano())
	password := "super_secret_kamehameha"

	// 1. Register new account
	acc, err := repo.Register(ctx, username, password)
	require.NoError(t, err)
	assert.NotEmpty(t, acc.ID)
	assert.Equal(t, username, acc.Username)

	// 2. Register duplicate username -> must fail
	_, err = repo.Register(ctx, username, password)
	assert.ErrorIs(t, err, session.ErrAccountExists)

	// 3. Authenticate with correct credentials
	authed, err := repo.Authenticate(ctx, username, password)
	require.NoError(t, err)
	assert.Equal(t, acc.ID, authed.ID)
	assert.Equal(t, username, authed.Username)

	// 4. Authenticate with invalid password
	_, err = repo.Authenticate(ctx, username, "wrong_password")
	assert.ErrorIs(t, err, session.ErrInvalidCredentials)

	// 5. Authenticate with nonexistent user
	_, err = repo.Authenticate(ctx, "nonexistent_saiyan", password)
	assert.ErrorIs(t, err, session.ErrInvalidCredentials)

	// 6. Add roles for account
	role1 := &session.Role{
		Name:     fmt.Sprintf("Vegeta_%d", time.Now().UnixNano()%10000),
		HeroCode: "10060",
		Level:    50,
		Gender:   1,
		Status:   0,
		Vip:      2,
		Guild:    "Z-Fighters",
	}
	err = repo.AddRole(ctx, acc.ID, role1)
	require.NoError(t, err)
	assert.NotEmpty(t, role1.ID)

	// 7. Duplicate role name for same account must fail
	err = repo.AddRole(ctx, acc.ID, role1)
	assert.Error(t, err)

	// 8. Retrieve roles (starter character + added role1)
	roles, err := repo.GetRoles(ctx, acc.ID)
	require.NoError(t, err)
	require.Len(t, roles, 2)
	assert.Equal(t, username, roles[0].Name)
	assert.Equal(t, "10001", roles[0].HeroCode)
	assert.Equal(t, role1.Name, roles[1].Name)
	assert.Equal(t, role1.HeroCode, roles[1].HeroCode)
	assert.Equal(t, int16(50), roles[1].Level)
}

func TestSessionRepository(t *testing.T) {
	setupTestDB(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := postgres.NewPool(ctx, postgres.DefaultPoolConfig(testDSN))
	require.NoError(t, err)
	defer pool.Close()

	accRepo := postgres.NewPostgresAccountRepository(pool)
	sessRepo := postgres.NewPostgresSessionRepository(pool)

	username := fmt.Sprintf("session_user_%d", time.Now().UnixNano())
	acc, err := accRepo.Register(ctx, username, "password123")
	require.NoError(t, err)

	role := &session.Role{
		Name:     fmt.Sprintf("Goku_%d", time.Now().UnixNano()%10000),
		HeroCode: "10001",
		Level:    1,
	}
	err = accRepo.AddRole(ctx, acc.ID, role)
	require.NoError(t, err)

	// 1. Create and save session
	sess := session.NewSession(acc, []*session.Role{role}, "conn-test-1", 1*time.Hour)
	err = sessRepo.SaveSession(ctx, sess)
	require.NoError(t, err)

	// 2. Retrieve session
	rec, err := sessRepo.GetSession(ctx, sess.Token())
	require.NoError(t, err)
	assert.Equal(t, sess.Token(), rec.Token)
	assert.Equal(t, acc.ID, rec.AccountID)
	assert.Equal(t, "conn-test-1", rec.ConnID)
	assert.Equal(t, "AUTHENTICATED", rec.State)
	assert.Nil(t, rec.SelectedRoleID)

	// 3. Update session state and selected role
	err = sessRepo.UpdateSelectedRole(ctx, sess.Token(), role.ID)
	require.NoError(t, err)
	err = sessRepo.UpdateSessionState(ctx, sess.Token(), session.StateInWorld, time.Now().UTC())
	require.NoError(t, err)

	rec2, err := sessRepo.GetSession(ctx, sess.Token())
	require.NoError(t, err)
	assert.Equal(t, "IN_WORLD", rec2.State)
	require.NotNil(t, rec2.SelectedRoleID)
	assert.Equal(t, role.ID, *rec2.SelectedRoleID)

	// 4. Duplicate login eviction
	sess2 := session.NewSession(acc, []*session.Role{role}, "conn-test-2", 1*time.Hour)
	err = sessRepo.SaveSession(ctx, sess2)
	require.NoError(t, err)

	evictedCount, err := sessRepo.EvictAccountSessions(ctx, acc.ID, sess2.Token())
	require.NoError(t, err)
	assert.Equal(t, int64(1), evictedCount)

	recEvicted, err := sessRepo.GetSession(ctx, sess.Token())
	require.NoError(t, err)
	assert.Equal(t, "EVICTED", recEvicted.State)

	recActive, err := sessRepo.GetSession(ctx, sess2.Token())
	require.NoError(t, err)
	assert.Equal(t, "AUTHENTICATED", recActive.State)

	// 5. Delete expired sessions
	deleted, err := sessRepo.DeleteExpiredSessions(ctx, time.Now().UTC().Add(48*time.Hour))
	require.NoError(t, err)
	assert.GreaterOrEqual(t, deleted, int64(2))
}

func TestRosterRepository(t *testing.T) {
	setupTestDB(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := postgres.NewPool(ctx, postgres.DefaultPoolConfig(testDSN))
	require.NoError(t, err)
	defer pool.Close()

	accRepo := postgres.NewPostgresAccountRepository(pool)
	rosterRepo := postgres.NewPostgresRosterRepository(pool)

	acc, err := accRepo.Register(ctx, fmt.Sprintf("roster_user_%d", time.Now().UnixNano()), "pass")
	require.NoError(t, err)

	// Test donor hero 10081 (Android 21 Good)
	heroID := int32(10081)

	// Initially locked
	unlocked, err := rosterRepo.IsUnlocked(ctx, acc.ID, heroID)
	require.NoError(t, err)
	assert.False(t, unlocked)

	// Grant unlock
	err = rosterRepo.GrantUnlock(ctx, acc.ID, heroID, "EVENT_CAMPAIGN")
	require.NoError(t, err)

	// Now unlocked
	unlocked, err = rosterRepo.IsUnlocked(ctx, acc.ID, heroID)
	require.NoError(t, err)
	assert.True(t, unlocked)

	// Unlocked list contains 10081
	heroes, err := rosterRepo.GetUnlockedHeroes(ctx, acc.ID)
	require.NoError(t, err)
	assert.Contains(t, heroes, heroID)

	// Revoke unlock
	err = rosterRepo.RevokeUnlock(ctx, acc.ID, heroID)
	require.NoError(t, err)

	unlocked, err = rosterRepo.IsUnlocked(ctx, acc.ID, heroID)
	require.NoError(t, err)
	assert.False(t, unlocked)
}

func TestInventoryRepository_AtomicTransfer(t *testing.T) {
	setupTestDB(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := postgres.NewPool(ctx, postgres.DefaultPoolConfig(testDSN))
	require.NoError(t, err)
	defer pool.Close()

	accRepo := postgres.NewPostgresAccountRepository(pool)
	invRepo := postgres.NewPostgresInventoryRepository(pool)

	acc, err := accRepo.Register(ctx, fmt.Sprintf("inv_user_%d", time.Now().UnixNano()), "pass")
	require.NoError(t, err)

	role1 := &session.Role{Name: fmt.Sprintf("Sender_%d", time.Now().UnixNano()%10000), HeroCode: "10001"}
	err = accRepo.AddRole(ctx, acc.ID, role1)
	require.NoError(t, err)

	role2 := &session.Role{Name: fmt.Sprintf("Receiver_%d", time.Now().UnixNano()%10000), HeroCode: "10002"}
	err = accRepo.AddRole(ctx, acc.ID, role2)
	require.NoError(t, err)

	// 1. Initial inventory setup
	itemID := 9001 // Senzu Bean
	err = invRepo.SetItem(ctx, role1.ID, 0, itemID, 10)
	require.NoError(t, err)

	item, err := invRepo.GetItem(ctx, role1.ID, 0)
	require.NoError(t, err)
	assert.Equal(t, itemID, item.ItemID)
	assert.Equal(t, 10, item.Count)

	// 2. Transfer 4 items from role1 slot 0 to role2 slot 0
	err = invRepo.TransferItem(ctx, role1.ID, 0, role2.ID, 0, 4)
	require.NoError(t, err)

	// Verify source has 6 left
	item1, err := invRepo.GetItem(ctx, role1.ID, 0)
	require.NoError(t, err)
	assert.Equal(t, 6, item1.Count)

	// Verify target has 4
	item2, err := invRepo.GetItem(ctx, role2.ID, 0)
	require.NoError(t, err)
	assert.Equal(t, 4, item2.Count)

	// 3. Transfer remaining 6 items to combine into target slot 0
	err = invRepo.TransferItem(ctx, role1.ID, 0, role2.ID, 0, 6)
	require.NoError(t, err)

	// Source slot should now be empty (deleted)
	_, err = invRepo.GetItem(ctx, role1.ID, 0)
	assert.ErrorIs(t, err, postgres.ErrItemNotFound)

	// Target slot should now have 10
	item2Combined, err := invRepo.GetItem(ctx, role2.ID, 0)
	require.NoError(t, err)
	assert.Equal(t, 10, item2Combined.Count)

	// 4. Test atomic failure and rollback: transfer 50 items (more than available 10)
	err = invRepo.TransferItem(ctx, role2.ID, 0, role1.ID, 0, 50)
	assert.ErrorIs(t, err, postgres.ErrInsufficientCount)

	// Verify target still has 10 and source is still empty (Zero uncommitted state ACK!)
	item2AfterFail, err := invRepo.GetItem(ctx, role2.ID, 0)
	require.NoError(t, err)
	assert.Equal(t, 10, item2AfterFail.Count)

	_, err = invRepo.GetItem(ctx, role1.ID, 0)
	assert.ErrorIs(t, err, postgres.ErrItemNotFound)
}

func TestWithTx_ExplicitRollback(t *testing.T) {
	setupTestDB(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := postgres.NewPool(ctx, postgres.DefaultPoolConfig(testDSN))
	require.NoError(t, err)
	defer pool.Close()

	accRepo := postgres.NewPostgresAccountRepository(pool)
	acc, err := accRepo.Register(ctx, fmt.Sprintf("tx_user_%d", time.Now().UnixNano()), "pass")
	require.NoError(t, err)

	role := &session.Role{Name: fmt.Sprintf("TxRole_%d", time.Now().UnixNano()%10000), HeroCode: "10001"}
	err = accRepo.AddRole(ctx, acc.ID, role)
	require.NoError(t, err)

	injectedErr := errors.New("simulated crash during transaction")

	// Attempt transaction that performs insert then returns error
	err = postgres.WithTx(ctx, pool, pgx.TxOptions{IsoLevel: pgx.ReadCommitted}, func(tx pgx.Tx) error {
		_, execErr := tx.Exec(ctx, `
			INSERT INTO player_inventories (role_id, slot, item_id, count, updated_at)
			VALUES ($1, 99, 9999, 50, NOW());`, role.ID)
		if execErr != nil {
			return execErr
		}
		// Injected failure triggers rollback
		return injectedErr
	})

	assert.ErrorIs(t, err, injectedErr)

	// Verify item was NOT inserted (Rollback verified!)
	invRepo := postgres.NewPostgresInventoryRepository(pool)
	_, err = invRepo.GetItem(ctx, role.ID, 99)
	assert.ErrorIs(t, err, postgres.ErrItemNotFound)
}

func TestWithTxRetry_HighConcurrency(t *testing.T) {
	setupTestDB(t)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	pool, err := postgres.NewPool(ctx, postgres.DefaultPoolConfig(testDSN))
	require.NoError(t, err)
	defer pool.Close()

	accRepo := postgres.NewPostgresAccountRepository(pool)
	acc, err := accRepo.Register(ctx, fmt.Sprintf("retry_user_%d", time.Now().UnixNano()), "pass")
	require.NoError(t, err)

	role := &session.Role{Name: fmt.Sprintf("RetryRole_%d", time.Now().UnixNano()%10000), HeroCode: "10001"}
	err = accRepo.AddRole(ctx, acc.ID, role)
	require.NoError(t, err)

	invRepo := postgres.NewPostgresInventoryRepository(pool)
	err = invRepo.SetItem(ctx, role.ID, 0, 777, 0+1) // start with 1
	require.NoError(t, err)

	const goroutines = 20
	var wg sync.WaitGroup
	wg.Add(goroutines)

	// Concurrently increment item count using WithTxRetry with Serializable isolation level
	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			txErr := postgres.WithTxRetry(ctx, pool, pgx.TxOptions{IsoLevel: pgx.Serializable}, 30, func(tx pgx.Tx) error {
				var count int
				err := tx.QueryRow(ctx, "SELECT count FROM player_inventories WHERE role_id = $1 AND slot = 0", role.ID).Scan(&count)
				if err != nil {
					return err
				}
				_, err = tx.Exec(ctx, "UPDATE player_inventories SET count = count + 1 WHERE role_id = $1 AND slot = 0", role.ID)
				return err
			})
			assert.NoError(t, txErr)
		}()
	}

	wg.Wait()

	// Verify final count: 1 + 20 = 21 with zero transaction loss!
	item, err := invRepo.GetItem(ctx, role.ID, 0)
	require.NoError(t, err)
	assert.Equal(t, 1+goroutines, item.Count)
}

func TestProgressionRepository(t *testing.T) {
	setupTestDB(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := postgres.NewPool(ctx, postgres.DefaultPoolConfig(testDSN))
	require.NoError(t, err)
	defer pool.Close()

	accRepo := postgres.NewPostgresAccountRepository(pool)
	progRepo := postgres.NewPostgresProgressionRepository(pool)

	acc, err := accRepo.Register(ctx, fmt.Sprintf("prog_user_%d", time.Now().UnixNano()), "pass")
	require.NoError(t, err)

	role := &session.Role{Name: fmt.Sprintf("ProgRole_%d", time.Now().UnixNano()%10000), HeroCode: "10001"}
	err = accRepo.AddRole(ctx, acc.ID, role)
	require.NoError(t, err)

	// Default progression for new character
	p, err := progRepo.GetProgression(ctx, role.ID)
	require.NoError(t, err)
	assert.Equal(t, role.ID, p.RoleID)
	assert.Equal(t, 1, p.StageID)
	assert.Equal(t, 0, p.StageProgress)
	assert.Equal(t, 0, p.Stars)

	// Save updated progression
	err = progRepo.SaveProgression(ctx, role.ID, 5, 3, 15)
	require.NoError(t, err)

	pUpdated, err := progRepo.GetProgression(ctx, role.ID)
	require.NoError(t, err)
	assert.Equal(t, 5, pUpdated.StageID)
	assert.Equal(t, 3, pUpdated.StageProgress)
	assert.Equal(t, 15, pUpdated.Stars)
}
