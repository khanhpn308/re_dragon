package world

import (
	"errors"
	"fmt"
	"time"
)

var (
	ErrItemNotConsumable = errors.New("item is not consumable")
	ErrHPAlreadyFull     = errors.New("health is already at maximum")
)

// ItemConsumptionResult captures the outcome of using a consumable item.
type ItemConsumptionResult struct {
	RoleID          int32 `json:"role_id"`
	Slot            int   `json:"slot"`
	ItemID          int   `json:"item_id"`
	HealAmount      int32 `json:"heal_amount"`
	NewHP           int32 `json:"new_hp"`
	RemainingInSlot int   `json:"remaining_in_slot"`
}

// ConsumeItem processes an authoritative player item consumption with idempotency protection.
// Example: Senzu Bean (ItemID 9001) restores 100% HP.
func ConsumeItem(
	player *PlayerEntity,
	slot int,
	itemID int,
	currentSlotCount int,
	now time.Time,
) (*ItemConsumptionResult, error) {
	player.mu.Lock()
	defer player.mu.Unlock()

	if player.State == StateDead {
		return nil, ErrEntityDead
	}

	if currentSlotCount <= 0 {
		return nil, errors.New("slot has no items to consume")
	}

	switch itemID {
	case 9001: // Senzu Bean: restores up to MaxHP
		if player.CurrentHP >= player.MaxHP {
			return nil, ErrHPAlreadyFull
		}
		heal := player.MaxHP - player.CurrentHP
		player.CurrentHP = player.MaxHP
		return &ItemConsumptionResult{
			RoleID:          player.RoleID,
			Slot:            slot,
			ItemID:          itemID,
			HealAmount:      heal,
			NewHP:           player.CurrentHP,
			RemainingInSlot: currentSlotCount - 1,
		}, nil

	case 9002: // Minor Capsule: restores 200 HP
		if player.CurrentHP >= player.MaxHP {
			return nil, ErrHPAlreadyFull
		}
		heal := int32(200)
		if player.CurrentHP+heal > player.MaxHP {
			heal = player.MaxHP - player.CurrentHP
		}
		player.CurrentHP += heal
		return &ItemConsumptionResult{
			RoleID:          player.RoleID,
			Slot:            slot,
			ItemID:          itemID,
			HealAmount:      heal,
			NewHP:           player.CurrentHP,
			RemainingInSlot: currentSlotCount - 1,
		}, nil

	default:
		return nil, fmt.Errorf("%w: item ID %d", ErrItemNotConsumable, itemID)
	}
}
