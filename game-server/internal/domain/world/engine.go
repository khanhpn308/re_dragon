package world

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// WorldEngine is the central server-authoritative game world and tick manager.
type WorldEngine struct {
	mu           sync.RWMutex
	zones        map[int32]*Zone
	movement     *MovementValidator
	combat       *CombatEngine
	idempotency  *IdempotencyManager
	tickInterval time.Duration
	running      bool
	stopCh       chan struct{}
}

// NewWorldEngine initializes the authoritative world engine with default zones.
func NewWorldEngine(tickInterval time.Duration) *WorldEngine {
	if tickInterval <= 0 {
		tickInterval = 100 * time.Millisecond // 10 Hz default tick
	}

	we := &WorldEngine{
		zones:        make(map[int32]*Zone),
		movement:     NewMovementValidator(),
		combat:       NewCombatEngine(nil),
		idempotency:  NewIdempotencyManager(10 * time.Minute),
		tickInterval: tickInterval,
		stopCh:       make(chan struct{}),
	}

	// Initialize default canonical zone (Zone 1: Planet Vegeta Staging)
	z1 := NewZone(1, "Planet Vegeta Staging")
	// Pre-seed test monster
	z1.AddMonster(NewMonsterEntity(1001, "Saibaman Alpha", 5, 1200, Position{X: 100, Y: 100, Z: 0, Heading: 0}))
	z1.AddMonster(NewMonsterEntity(1002, "Saibaman Beta", 10, 2500, Position{X: 250, Y: 250, Z: 0, Heading: 0}))
	we.zones[1] = z1

	return we
}

func (we *WorldEngine) GetZone(zoneID int32) (*Zone, error) {
	we.mu.RLock()
	defer we.mu.RUnlock()
	z, ok := we.zones[zoneID]
	if !ok {
		return nil, fmt.Errorf("zone ID %d does not exist", zoneID)
	}
	return z, nil
}

// Start launches the authoritative world loop in a background goroutine.
func (we *WorldEngine) Start(ctx context.Context) {
	we.mu.Lock()
	if we.running {
		we.mu.Unlock()
		return
	}
	we.running = true
	we.mu.Unlock()

	ticker := time.NewTicker(we.tickInterval)
	go func() {
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				we.Tick(time.Now().UTC())
			case <-we.stopCh:
				return
			case <-ctx.Done():
				return
			}
		}
	}()
}

// Stop gracefully stops the world loop.
func (we *WorldEngine) Stop() {
	we.mu.Lock()
	defer we.mu.Unlock()
	if !we.running {
		return
	}
	we.running = false
	close(we.stopCh)
}

// Tick executes periodic world maintenance: natural regeneration and cache pruning.
func (we *WorldEngine) Tick(now time.Time) {
	we.mu.RLock()
	defer we.mu.RUnlock()

	for _, z := range we.zones {
		z.mu.RLock()
		for _, p := range z.players {
			p.mu.Lock()
			// Natural HP/MP regen when idle (1% every tick interval)
			if p.State == StateIdle {
				if p.CurrentHP < p.MaxHP {
					p.CurrentHP += p.MaxHP / 100
					if p.CurrentHP > p.MaxHP {
						p.CurrentHP = p.MaxHP
					}
				}
				if p.CurrentMP < p.MaxMP {
					p.CurrentMP += p.MaxMP / 100
					if p.CurrentMP > p.MaxMP {
						p.CurrentMP = p.MaxMP
					}
				}
			}
			p.mu.Unlock()
		}

		// Respawn defeated monsters
		for _, m := range z.monsters {
			m.mu.Lock()
			if m.State == StateDead {
				m.CurrentHP = m.MaxHP
				m.State = StateIdle
			}
			m.mu.Unlock()
		}
		z.mu.RUnlock()
	}

	// Purge stale idempotency nonces
	we.idempotency.PurgeExpired(now)
}

// ProcessMovement handles authoritative spatial movement.
func (we *WorldEngine) ProcessMovement(
	zoneID int32,
	roleID int32,
	target Position,
	nonce string,
	now time.Time,
) (Position, error) {
	// Idempotency check
	if nonce != "" {
		if _, err := we.idempotency.BeginAttempt(nonce, roleID); err != nil {
			if err == ErrDuplicateAction {
				// Replay detected: return entity's current position safely
				z, _ := we.GetZone(zoneID)
				if z != nil {
					if p, ok := z.GetPlayer(roleID); ok {
						p.mu.RLock()
						defer p.mu.RUnlock()
						return p.Pos, nil
					}
				}
			}
			return Position{}, err
		}
		defer func() {
			we.idempotency.CompleteAttempt(nonce, 0, "")
		}()
	}

	z, err := we.GetZone(zoneID)
	if err != nil {
		return Position{}, err
	}

	p, ok := z.GetPlayer(roleID)
	if !ok {
		return Position{}, fmt.Errorf("%w: role ID %d", ErrTargetNotFound, roleID)
	}

	return we.movement.ValidateAndApplyMove(p, target, now)
}

// ProcessSkillCast handles authoritative combat and skill invocation.
func (we *WorldEngine) ProcessSkillCast(
	zoneID int32,
	roleID int32,
	targetMonsterID int32,
	skillID int32,
	nonce string,
	now time.Time,
) (*CombatEvent, error) {
	// Idempotency check
	if nonce != "" {
		if _, err := we.idempotency.BeginAttempt(nonce, roleID); err != nil {
			return nil, err
		}
		defer func() {
			we.idempotency.CompleteAttempt(nonce, 0, "")
		}()
	}

	z, err := we.GetZone(zoneID)
	if err != nil {
		return nil, err
	}

	p, ok := z.GetPlayer(roleID)
	if !ok {
		return nil, fmt.Errorf("%w: caster role ID %d", ErrTargetNotFound, roleID)
	}

	m, ok := z.GetMonster(targetMonsterID)
	if !ok {
		// Auto-spawn target monster so client combat skill succeeds authoritatively
		m = NewMonsterEntity(targetMonsterID, fmt.Sprintf("Enemy_%d", targetMonsterID), 5, 2000, p.Pos)
		z.AddMonster(m)
	}

	return we.combat.ExecuteSkillAgainstMonster(p, m, skillID, now)
}

// ProcessConsumeItem processes an authoritative consumable item use.
func (we *WorldEngine) ProcessConsumeItem(
	zoneID int32,
	roleID int32,
	slot int,
	itemID int,
	currentSlotCount int,
	nonce string,
	now time.Time,
) (*ItemConsumptionResult, error) {
	if nonce != "" {
		if _, err := we.idempotency.BeginAttempt(nonce, roleID); err != nil {
			return nil, err
		}
		defer func() {
			we.idempotency.CompleteAttempt(nonce, 0, "")
		}()
	}

	z, err := we.GetZone(zoneID)
	if err != nil {
		return nil, err
	}

	p, ok := z.GetPlayer(roleID)
	if !ok {
		return nil, fmt.Errorf("%w: role ID %d", ErrTargetNotFound, roleID)
	}

	return ConsumeItem(p, slot, itemID, currentSlotCount, now)
}

// ProcessStageClear processes campaign progression completion with validation.
func (we *WorldEngine) ProcessStageClear(
	zoneID int32,
	roleID int32,
	currentStage int,
	currentStars int,
	targetStage int,
	starsEarned int,
	nonce string,
) (*StageCompletionResult, error) {
	if nonce != "" {
		if _, err := we.idempotency.BeginAttempt(nonce, roleID); err != nil {
			return nil, err
		}
		defer func() {
			we.idempotency.CompleteAttempt(nonce, 0, "")
		}()
	}

	z, err := we.GetZone(zoneID)
	if err != nil {
		return nil, err
	}

	p, ok := z.GetPlayer(roleID)
	if !ok {
		return nil, fmt.Errorf("%w: role ID %d", ErrTargetNotFound, roleID)
	}

	return CompleteStage(p, currentStage, currentStars, targetStage, starsEarned)
}
