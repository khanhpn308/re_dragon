package world

import (
	"errors"
	"fmt"
)

var (
	ErrInvalidStageJump   = errors.New("cannot skip stages: previous stage must be completed first")
	ErrInvalidStarsEarned = errors.New("stars earned must be between 1 and 3")
)

type StageCompletionResult struct {
	RoleID          int32 `json:"role_id"`
	StageID         int   `json:"stage_id"`
	StarsEarned     int   `json:"stars_earned"`
	TotalStars      int   `json:"total_stars"`
	ExpAwarded      int64 `json:"exp_awarded"`
	NewLevel        int16 `json:"new_level"`
	LevelUpOccurred bool  `json:"level_up_occurred"`
}

// CompleteStage validates and processes authoritative stage completion.
func CompleteStage(
	player *PlayerEntity,
	currentStageID int,
	currentTotalStars int,
	targetStageID int,
	starsEarned int,
) (*StageCompletionResult, error) {
	player.mu.Lock()
	defer player.mu.Unlock()

	if player.State == StateDead {
		return nil, ErrEntityDead
	}

	if starsEarned < 1 || starsEarned > 3 {
		return nil, ErrInvalidStarsEarned
	}

	// Player can only complete current stage or immediately next stage
	if targetStageID > currentStageID+1 {
		return nil, fmt.Errorf("%w: requested stage %d, max unlocked %d",
			ErrInvalidStageJump, targetStageID, currentStageID+1)
	}

	// Deterministic EXP grant: 100 * StageID
	expAwarded := int64(targetStageID * 100)
	levelUp := false
	newLevel := player.Level

	// Simple deterministic milestone level calculation
	if targetStageID%5 == 0 && player.Level < 100 {
		player.Level++
		newLevel = player.Level
		levelUp = true
		player.MaxHP = int32(1000 + int(player.Level)*250)
		player.CurrentHP = player.MaxHP
	}

	return &StageCompletionResult{
		RoleID:          player.RoleID,
		StageID:         targetStageID,
		StarsEarned:     starsEarned,
		TotalStars:      currentTotalStars + starsEarned,
		ExpAwarded:      expAwarded,
		NewLevel:        newLevel,
		LevelUpOccurred: levelUp,
	}, nil
}
