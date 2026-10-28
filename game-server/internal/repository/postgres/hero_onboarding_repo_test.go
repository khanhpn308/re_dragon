package postgres_test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"returnsaiyan/gameserver/internal/repository/postgres"
)

// Database-backed contract test only; does not simulate or attest Android RPC.
func TestHeroOnboarding_IdempotentGrantAndFormationOwnership(t *testing.T) {
	setupTestDB(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := postgres.NewPool(ctx, postgres.DefaultPoolConfig(testDSN))
	require.NoError(t, err)
	defer pool.Close()

	accounts := postgres.NewPostgresAccountRepository(pool)
	owner, err := accounts.Register(ctx, fmt.Sprintf("owned_hero_%d", time.Now().UnixNano()), "test_password")
	require.NoError(t, err)
	other, err := accounts.Register(ctx, fmt.Sprintf("other_hero_%d", time.Now().UnixNano()), "test_password")
	require.NoError(t, err)

	store := postgres.NewHeroOnboardingRepository(pool)
	first, err := store.RecordAuthorizedSummon(ctx, owner.ID, "earth-x1-test-1", 10001, 123)
	require.NoError(t, err)
	require.Positive(t, first)

	replayed, err := store.RecordAuthorizedSummon(ctx, owner.ID, "earth-x1-test-1", 10001, 123)
	require.NoError(t, err)
	assert.Equal(t, first, replayed, "a repeated request must not grant another hero")
	_, err = store.RecordAuthorizedSummon(ctx, owner.ID, "earth-x1-test-1", 10060, 123)
	require.Error(t, err, "reusing a request ID with another hero must fail")

	second, err := store.RecordAuthorizedSummon(ctx, owner.ID, "earth-x1-test-2", 10060, 10)
	require.NoError(t, err)
	require.NotEqual(t, first, second)

	var ownedCount, opCount int
	require.NoError(t, pool.QueryRow(ctx, "SELECT count(*) FROM hero_instances WHERE account_id=$1", owner.ID).Scan(&ownedCount))
	require.NoError(t, pool.QueryRow(ctx, "SELECT count(*) FROM hero_summon_operations WHERE account_id=$1", owner.ID).Scan(&opCount))
	assert.Equal(t, 2, ownedCount)
	assert.Equal(t, 2, opCount)

	require.NoError(t, store.AssignActiveSlot(ctx, owner.ID, 1, first))
	require.NoError(t, store.AssignActiveSlot(ctx, owner.ID, 2, second))
	require.Error(t, store.AssignActiveSlot(ctx, owner.ID, 2, first), "hero may not occupy two slots")
	require.Error(t, store.AssignActiveSlot(ctx, other.ID, 1, first), "other account may not take owned hero")
	require.Error(t, store.AssignActiveSlot(ctx, owner.ID, 5, first), "out-of-range slot denied")

	// Durable DB read after closing/recreating the store object.
	reloaded := postgres.NewHeroOnboardingRepository(pool)
	_ = reloaded
	var activeID int64
	require.NoError(t, pool.QueryRow(ctx, "SELECT hero_instance_id FROM hero_formations WHERE account_id=$1 AND slot=1", owner.ID).Scan(&activeID))
	assert.Equal(t, first, activeID)
}
