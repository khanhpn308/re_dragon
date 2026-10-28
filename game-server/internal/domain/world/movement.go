package world

import (
	"errors"
	"fmt"
	"time"
)

var (
	ErrEntityDead         = errors.New("cannot perform action while dead")
	ErrSpeedHackDetected  = errors.New("movement speed exceeds authoritative limit (speed hack detected)")
	ErrInvalidCoordinates = errors.New("invalid or NaN/Inf spatial coordinates")
)

// MovementValidator enforces server-authoritative spatial bounds and speed limits.
type MovementValidator struct {
	MaxSpeedBuffer float32 // Extra tolerance buffer for network jitter (default 50.0 units)
	MaxLagSeconds  float32 // Maximum allowed client time discrepancy (default 2.0s)
}

func NewMovementValidator() *MovementValidator {
	return &MovementValidator{
		MaxSpeedBuffer: 50.0,
		MaxLagSeconds:  2.0,
	}
}

// ValidateAndApplyMove validates movement from current entity position to target position.
// If valid, updates entity position deterministically.
// If invalid, rejects and preserves current authoritative position.
func (v *MovementValidator) ValidateAndApplyMove(
	entity *PlayerEntity,
	target Position,
	now time.Time,
) (Position, error) {
	entity.mu.Lock()
	defer entity.mu.Unlock()

	if entity.State == StateDead {
		return entity.Pos, ErrEntityDead
	}

	// 1. Validate coordinate sanity (no NaN or Inf)
	if target.X != target.X || target.Y != target.Y || target.Z != target.Z {
		return entity.Pos, ErrInvalidCoordinates
	}

	// 2. Calculate distance
	dist := entity.Pos.Distance(target)
	if dist < 0.001 {
		// Zero movement or standing in place
		entity.Pos.Heading = target.Heading
		entity.State = StateIdle
		return entity.Pos, nil
	}

	// 3. Calculate elapsed time
	elapsed := float32(now.Sub(entity.LastMoveTime).Seconds())
	if elapsed <= 0 {
		elapsed = 0.05 // default 50ms tick floor for burst packets
	}
	if elapsed > v.MaxLagSeconds {
		elapsed = v.MaxLagSeconds
	}

	// 4. Calculate maximum allowable distance = (speed * elapsed) + buffer
	maxAllowedDist := (entity.MoveSpeed * elapsed) + v.MaxSpeedBuffer
	if dist > maxAllowedDist {
		// Speed hack or teleportation detected: snap back to current authoritative position
		return entity.Pos, fmt.Errorf("%w: distance %.2f exceeds max allowed %.2f (speed %.1f, elapsed %.3fs)",
			ErrSpeedHackDetected, dist, maxAllowedDist, entity.MoveSpeed, elapsed)
	}

	// 5. Apply valid movement deterministically
	entity.Pos = target
	entity.LastMoveTime = now
	entity.State = StateMoving

	return entity.Pos, nil
}
