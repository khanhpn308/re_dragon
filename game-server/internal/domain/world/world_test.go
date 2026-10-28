package world_test

import (
	"context"
	"fmt"
	"math"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"returnsaiyan/gameserver/internal/domain/world"
)

func TestMovementValidation_LegalAndIllegal(t *testing.T) {
	validator := world.NewMovementValidator()
	now := time.Now().UTC()

	// Initial player at (0, 0, 0) with speed 350.0 units/sec
	p := world.NewPlayerEntity(1, "vegeta_acc", "Vegeta", "10060", 50, "conn-1", world.Position{X: 0, Y: 0, Z: 0, Heading: 0})
	p.LastMoveTime = now.Add(-1 * time.Second) // 1 second elapsed

	// 1. Legal Move: move 200 units in 1 second (speed 350 allows up to 350 + 50 = 400 units)
	targetLegal := world.Position{X: 200, Y: 0, Z: 0, Heading: 90}
	newPos, err := validator.ValidateAndApplyMove(p, targetLegal, now)
	require.NoError(t, err)
	assert.Equal(t, float32(200), newPos.X)
	assert.Equal(t, float32(0), newPos.Y)

	// 2. Illegal Move (Speed Hack): attempt to move 1000 units in 0.1s
	illegalTime := now.Add(100 * time.Millisecond)
	targetIllegal := world.Position{X: 1200, Y: 0, Z: 0, Heading: 90}
	snapPos, err := validator.ValidateAndApplyMove(p, targetIllegal, illegalTime)
	assert.ErrorIs(t, err, world.ErrSpeedHackDetected)
	// Must snap back to previous authoritative position (200, 0, 0)
	assert.Equal(t, float32(200), snapPos.X)

	// 3. Coordinate Sanity (NaN / Inf rejection)
	targetNaN := world.Position{X: float32(math.NaN()), Y: 0, Z: 0, Heading: 0}
	_, err = validator.ValidateAndApplyMove(p, targetNaN, now.Add(1*time.Second))
	assert.ErrorIs(t, err, world.ErrInvalidCoordinates)

	// 4. Dead player cannot move
	p.State = world.StateDead
	_, err = validator.ValidateAndApplyMove(p, world.Position{X: 250, Y: 0, Z: 0}, now.Add(2*time.Second))
	assert.ErrorIs(t, err, world.ErrEntityDead)
}

func TestCombatEngine_SkillExecutionAndCooldown(t *testing.T) {
	engine := world.NewCombatEngine(nil)
	now := time.Now().UTC()

	// Player at (0, 0) and Monster at (100, 0) -> distance = 100 (well within Kamehameha range 600)
	p := world.NewPlayerEntity(1, "goku_acc", "Goku", "10001", 10, "conn-1", world.Position{X: 0, Y: 0, Z: 0, Heading: 0})
	m := world.NewMonsterEntity(1001, "Saibaman", 5, 1000, world.Position{X: 100, Y: 0, Z: 0, Heading: 0})

	initialMP := p.CurrentMP
	initialHP := m.CurrentHP

	// 1. Cast Kamehameha (Skill ID 101, Cost 50, Cooldown 1.5s, BaseDamage 300)
	event, err := engine.ExecuteSkillAgainstMonster(p, m, 101, now)
	require.NoError(t, err)
	assert.Equal(t, int32(1), event.CasterID)
	assert.Equal(t, int32(1001), event.TargetID)
	assert.Equal(t, "Kamehameha", event.SkillName)
	assert.True(t, event.UnknownFormulaUsed) // Transparency: flagged as UNKNOWN formula placeholder

	// Check deterministic cost application
	expectedDamage := int32(300 + 10*15) // 450 damage
	assert.Equal(t, expectedDamage, event.DamageDealt)
	assert.Equal(t, initialMP-50, p.CurrentMP)
	assert.Equal(t, initialHP-expectedDamage, m.CurrentHP)
	assert.False(t, event.TargetDied)

	// 2. Cooldown check: attempt to cast again at now + 500ms (cooldown is 1500ms)
	_, err = engine.ExecuteSkillAgainstMonster(p, m, 101, now.Add(500*time.Millisecond))
	assert.ErrorIs(t, err, world.ErrSkillOnCooldown)

	// 3. Out of Range check: move monster to (1000, 0) -> distance 1000 > 625 max range
	m.Pos = world.Position{X: 1000, Y: 0, Z: 0, Heading: 0}
	_, err = engine.ExecuteSkillAgainstMonster(p, m, 101, now.Add(2*time.Second))
	assert.ErrorIs(t, err, world.ErrTargetOutOfRange)

	// 4. Insufficient Mana check
	p.CurrentMP = 10 // Need 50
	m.Pos = world.Position{X: 100, Y: 0, Z: 0, Heading: 0}
	_, err = engine.ExecuteSkillAgainstMonster(p, m, 101, now.Add(2*time.Second))
	assert.ErrorIs(t, err, world.ErrInsufficientMana)

	// 5. Defeat monster check
	p.CurrentMP = 500
	m.CurrentHP = 200 // Less than damage 450
	eventFatal, err := engine.ExecuteSkillAgainstMonster(p, m, 101, now.Add(4*time.Second))
	require.NoError(t, err)
	assert.True(t, eventFatal.TargetDied)
	assert.Equal(t, int32(0), m.CurrentHP)
	assert.Equal(t, world.StateDead, m.State)

	// 6. Targeting defeated monster must fail
	_, err = engine.ExecuteSkillAgainstMonster(p, m, 101, now.Add(6*time.Second))
	assert.ErrorIs(t, err, world.ErrTargetDead)
}

func TestIdempotencyManager(t *testing.T) {
	mgr := world.NewIdempotencyManager(5 * time.Minute)

	nonce := "action_nonce_777888"
	roleID := int32(42)

	// 1. Initial attempt
	rec, err := mgr.BeginAttempt(nonce, roleID)
	require.NoError(t, err)
	assert.Equal(t, nonce, rec.Key)
	assert.Equal(t, world.ActionPending, rec.Status)

	// 2. Complete attempt
	mgr.CompleteAttempt(nonce, 200, "")

	// 3. Replay with same nonce -> must be detected as duplicate
	recDup, err := mgr.BeginAttempt(nonce, roleID)
	assert.ErrorIs(t, err, world.ErrDuplicateAction)
	assert.Equal(t, int32(200), recDup.ResultCode)

	// 4. Purge expired nonces
	purged := mgr.PurgeExpired(time.Now().UTC().Add(10 * time.Minute))
	assert.Equal(t, 1, purged)
}

func TestInventoryAction_ConsumeItem(t *testing.T) {
	now := time.Now().UTC()
	p := world.NewPlayerEntity(1, "goku", "Goku", "10001", 10, "conn-1", world.Position{})
	p.CurrentHP = 500 // MaxHP is 1000 + 10*250 = 3500

	// 1. Consume Senzu Bean (9001)
	res, err := world.ConsumeItem(p, 0, 9001, 3, now)
	require.NoError(t, err)
	assert.Equal(t, int32(3500), res.NewHP)
	assert.Equal(t, int32(3000), res.HealAmount)
	assert.Equal(t, 2, res.RemainingInSlot)

	// 2. Consume at full health -> must fail with ErrHPAlreadyFull
	_, err = world.ConsumeItem(p, 0, 9001, 2, now)
	assert.ErrorIs(t, err, world.ErrHPAlreadyFull)

	// 3. Non-consumable item
	p.CurrentHP = 1000
	_, err = world.ConsumeItem(p, 1, 8888, 1, now)
	assert.ErrorIs(t, err, world.ErrItemNotConsumable)
}

func TestProgressionAction_CompleteStage(t *testing.T) {
	p := world.NewPlayerEntity(1, "goku", "Goku", "10001", 10, "conn-1", world.Position{})

	// 1. Complete Stage 1 with 3 stars
	res, err := world.CompleteStage(p, 0, 0, 1, 3)
	require.NoError(t, err)
	assert.Equal(t, 1, res.StageID)
	assert.Equal(t, 3, res.StarsEarned)
	assert.Equal(t, 3, res.TotalStars)
	assert.Equal(t, int64(100), res.ExpAwarded)

	// 2. Stage jumping: attempt to clear stage 10 while only at stage 1
	_, err = world.CompleteStage(p, 1, 3, 10, 3)
	assert.ErrorIs(t, err, world.ErrInvalidStageJump)

	// 3. Invalid star count (<1 or >3)
	_, err = world.CompleteStage(p, 1, 3, 2, 5)
	assert.ErrorIs(t, err, world.ErrInvalidStarsEarned)
}

func TestWorldEngine_ConcurrentActions(t *testing.T) {
	engine := world.NewWorldEngine(50 * time.Millisecond)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	engine.Start(ctx)
	defer engine.Stop()

	zone, err := engine.GetZone(1)
	require.NoError(t, err)

	const playerCount = 20
	// Pre-seed players in zone
	for i := 1; i <= playerCount; i++ {
		p := world.NewPlayerEntity(int32(i), fmt.Sprintf("saiyan_%d", i), fmt.Sprintf("Role_%d", i), "10001", 20, fmt.Sprintf("conn-%d", i), world.Position{X: float32(i * 10), Y: float32(i * 10)})
		err := zone.AddPlayer(p)
		require.NoError(t, err)
	}

	var wg sync.WaitGroup
	wg.Add(playerCount)

	// Concurrently perform movement, skill casts, and item consumption across 20 players
	for i := 1; i <= playerCount; i++ {
		roleID := int32(i)
		go func(id int32) {
			defer wg.Done()
			now := time.Now().UTC()

			// 1. Move player
			target := world.Position{X: float32(id*10 + 20), Y: float32(id*10 + 20), Z: 0, Heading: 45}
			moveNonce := fmt.Sprintf("move_nonce_%d", id)
			_, err := engine.ProcessMovement(1, id, target, moveNonce, now.Add(500*time.Millisecond))
			assert.NoError(t, err)

			// 2. Cast Skill on Saibaman Alpha (ID 1001)
			skillNonce := fmt.Sprintf("skill_nonce_%d", id)
			// Note: only some players may be in range or have cooldown; test ensures zero panic or race condition
			_, _ = engine.ProcessSkillCast(1, id, 1001, 101, skillNonce, now.Add(600*time.Millisecond))

			// 3. Consume Item
			itemNonce := fmt.Sprintf("item_nonce_%d", id)
			_, _ = engine.ProcessConsumeItem(1, id, 0, 9002, 5, itemNonce, now.Add(700*time.Millisecond))
		}(roleID)
	}

	wg.Wait()
}

func TestWorldEngine_NaturalRegeneration(t *testing.T) {
	engine := world.NewWorldEngine(50 * time.Millisecond)
	zone, err := engine.GetZone(1)
	require.NoError(t, err)

	p := world.NewPlayerEntity(99, "regen_saiyan", "Piccolo", "10002", 10, "conn-99", world.Position{})
	p.CurrentHP = 1000
	p.CurrentMP = 500
	p.State = world.StateIdle
	err = zone.AddPlayer(p)
	require.NoError(t, err)

	// Run 5 ticks
	for i := 0; i < 5; i++ {
		engine.Tick(time.Now().UTC())
	}

	// Verify HP and MP regenerated deterministically
	assert.Greater(t, p.CurrentHP, int32(1000))
	assert.Greater(t, p.CurrentMP, int32(500))
}
