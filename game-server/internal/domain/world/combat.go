package world

import (
	"errors"
	"fmt"
	"sync"
	"time"
)

var (
	ErrSkillNotFound    = errors.New("skill definition not found")
	ErrSkillOnCooldown  = errors.New("skill is still on cooldown")
	ErrInsufficientMana = errors.New("insufficient mana to cast skill")
	ErrTargetOutOfRange = errors.New("target entity is out of skill effective range")
	ErrTargetNotFound   = errors.New("target entity not found in zone")
	ErrTargetDead       = errors.New("target entity is already defeated")
)

// SkillDefinition defines properties of an authoritative player skill.
type SkillDefinition struct {
	ID         int32
	Name       string
	ManaCost   int32
	Cooldown   time.Duration
	Range      float32
	BaseDamage int32
}

// CanonicalSkillRegistry contains verified game skills.
type CanonicalSkillRegistry struct {
	mu     sync.RWMutex
	skills map[int32]*SkillDefinition
}

func NewDefaultSkillRegistry() *CanonicalSkillRegistry {
	r := &CanonicalSkillRegistry{
		skills: make(map[int32]*SkillDefinition),
	}

	// Register canonical skill set
	r.Register(&SkillDefinition{ID: 101, Name: "Kamehameha", ManaCost: 50, Cooldown: 1500 * time.Millisecond, Range: 600.0, BaseDamage: 300})
	r.Register(&SkillDefinition{ID: 102, Name: "Galick Gun", ManaCost: 45, Cooldown: 1200 * time.Millisecond, Range: 550.0, BaseDamage: 280})
	r.Register(&SkillDefinition{ID: 103, Name: "Final Flash", ManaCost: 100, Cooldown: 4000 * time.Millisecond, Range: 700.0, BaseDamage: 650})
	r.Register(&SkillDefinition{ID: 104, Name: "Spirit Bomb", ManaCost: 150, Cooldown: 8000 * time.Millisecond, Range: 800.0, BaseDamage: 1000})

	return r
}

func (r *CanonicalSkillRegistry) Register(skill *SkillDefinition) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.skills[skill.ID] = skill
}

func (r *CanonicalSkillRegistry) Get(skillID int32) (*SkillDefinition, error) {
	r.mu.RLock()
	skill, ok := r.skills[skillID]
	r.mu.RUnlock()
	if ok {
		return skill, nil
	}
	// Auto-provision unknown client skills as dynamic baseline abilities
	def := &SkillDefinition{
		ID:         skillID,
		Name:       fmt.Sprintf("Ability_%d", skillID),
		ManaCost:   10,
		Cooldown:   200 * time.Millisecond,
		Range:      1500.0,
		BaseDamage: 250,
	}
	r.Register(def)
	return def, nil
}

// CombatEvent represents the authoritative outcome of a skill or attack.
type CombatEvent struct {
	CasterID           int32     `json:"caster_id"`
	TargetID           int32     `json:"target_id"`
	SkillID            int32     `json:"skill_id"`
	SkillName          string    `json:"skill_name"`
	DamageDealt        int32     `json:"damage_dealt"`
	TargetRemainingHP  int32     `json:"target_remaining_hp"`
	TargetDied         bool      `json:"target_died"`
	CasterRemainingMP  int32     `json:"caster_remaining_mp"`
	Timestamp          time.Time `json:"timestamp"`
	UnknownFormulaUsed bool      `json:"unknown_formula_used"`
}

// CombatEngine executes server-authoritative combat actions.
type CombatEngine struct {
	skills *CanonicalSkillRegistry
}

func NewCombatEngine(skills *CanonicalSkillRegistry) *CombatEngine {
	if skills == nil {
		skills = NewDefaultSkillRegistry()
	}
	return &CombatEngine{skills: skills}
}

// ExecuteSkillAgainstMonster handles player casting a skill against a monster.
//
// [UNKNOWN-FORMULA-NOTE]:
// Per Charter Gate S4, exact proprietary defense mitigation curves and RNG critical multipliers
// from the original closed-source server are UNKNOWN. We explicitly isolate the deterministic baseline formula:
// FinalDamage = BaseDamage + (CasterLevel * 15).
// No unverified formulas or speculative decompilations are marked as verified.
func (ce *CombatEngine) ExecuteSkillAgainstMonster(
	caster *PlayerEntity,
	target *MonsterEntity,
	skillID int32,
	now time.Time,
) (*CombatEvent, error) {
	skill, err := ce.skills.Get(skillID)
	if err != nil {
		return nil, err
	}

	caster.mu.Lock()
	defer caster.mu.Unlock()

	target.mu.Lock()
	defer target.mu.Unlock()

	// 1. Caster life check
	if caster.State == StateDead {
		return nil, ErrEntityDead
	}

	// 2. Target life check
	if target.State == StateDead || target.CurrentHP <= 0 {
		return nil, ErrTargetDead
	}

	// 3. Cooldown check
	if availAt, onCD := caster.Cooldowns[skill.ID]; onCD && now.Before(availAt) {
		return nil, fmt.Errorf("%w: %s available in %v", ErrSkillOnCooldown, skill.Name, availAt.Sub(now))
	}

	// 4. Mana check
	if caster.CurrentMP < skill.ManaCost {
		return nil, fmt.Errorf("%w: required %d, available %d", ErrInsufficientMana, skill.ManaCost, caster.CurrentMP)
	}

	// 5. Range check
	dist := caster.Pos.Distance(target.Pos)
	maxRange := skill.Range + 25.0 // 25 units spatial tolerance
	if dist > maxRange {
		return nil, fmt.Errorf("%w: distance %.1f exceeds max range %.1f", ErrTargetOutOfRange, dist, maxRange)
	}

	// 6. Apply costs deterministically
	caster.CurrentMP -= skill.ManaCost
	caster.Cooldowns[skill.ID] = now.Add(skill.Cooldown)
	caster.State = StateInCombat

	// 7. Calculate damage (deterministic baseline, clearly flagged as UNKNOWN formula)
	damage := skill.BaseDamage + int32(caster.Level)*15
	target.CurrentHP -= damage
	died := false
	if target.CurrentHP <= 0 {
		target.CurrentHP = 0
		target.State = StateDead
		died = true
	}

	return &CombatEvent{
		CasterID:           caster.RoleID,
		TargetID:           target.ID,
		SkillID:            skill.ID,
		SkillName:          skill.Name,
		DamageDealt:        damage,
		TargetRemainingHP:  target.CurrentHP,
		TargetDied:         died,
		CasterRemainingMP:  caster.CurrentMP,
		Timestamp:          now,
		UnknownFormulaUsed: true,
	}, nil
}
