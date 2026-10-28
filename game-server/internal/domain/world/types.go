package world

import (
	"math"
	"sync"
	"time"
)

// Position represents 3D spatial coordinates and heading in the game world.
type Position struct {
	X       float32 `json:"x"`
	Y       float32 `json:"y"`
	Z       float32 `json:"z"`
	Heading float32 `json:"heading"`
}

// Distance calculates the Euclidean distance between two positions in the horizontal plane (X, Y).
func (p Position) Distance(other Position) float32 {
	dx := p.X - other.X
	dy := p.Y - other.Y
	return float32(math.Sqrt(float64(dx*dx + dy*dy)))
}

// Distance3D calculates 3D Euclidean distance.
func (p Position) Distance3D(other Position) float32 {
	dx := p.X - other.X
	dy := p.Y - other.Y
	dz := p.Z - other.Z
	return float32(math.Sqrt(float64(dx*dx + dy*dy + dz*dz)))
}

type EntityState int

const (
	StateIdle EntityState = iota
	StateMoving
	StateInCombat
	StateDead
)

// PlayerEntity represents an active player character inside a game world zone.
type PlayerEntity struct {
	mu           sync.RWMutex
	RoleID       int32
	AccountName  string
	RoleName     string
	HeroCode     string
	Level        int16
	MaxHP        int32
	CurrentHP    int32
	MaxMP        int32
	CurrentMP    int32
	Pos          Position
	MoveSpeed    float32 // Units per second (default: 350.0)
	LastMoveTime time.Time
	State        EntityState
	ConnID       string
	Cooldowns    map[int32]time.Time // skillID -> availableAt
}

// NewPlayerEntity creates a new player entity initialized at the given spawn position.
func NewPlayerEntity(
	roleID int32,
	accountName string,
	roleName string,
	heroCode string,
	level int16,
	connID string,
	spawnPos Position,
) *PlayerEntity {
	maxHP := int32(1000 + int(level)*250)
	maxMP := int32(500 + int(level)*100)

	return &PlayerEntity{
		RoleID:       roleID,
		AccountName:  accountName,
		RoleName:     roleName,
		HeroCode:     heroCode,
		Level:        level,
		MaxHP:        maxHP,
		CurrentHP:    maxHP,
		MaxMP:        maxMP,
		CurrentMP:    maxMP,
		Pos:          spawnPos,
		MoveSpeed:    350.0,
		LastMoveTime: time.Now().UTC(),
		State:        StateIdle,
		ConnID:       connID,
		Cooldowns:    make(map[int32]time.Time),
	}
}

// MonsterEntity represents an NPC/monster target in the world.
type MonsterEntity struct {
	mu        sync.RWMutex
	ID        int32
	Name      string
	Level     int16
	MaxHP     int32
	CurrentHP int32
	Pos       Position
	State     EntityState
}

// NewMonsterEntity creates a test monster entity.
func NewMonsterEntity(id int32, name string, level int16, hp int32, pos Position) *MonsterEntity {
	return &MonsterEntity{
		ID:        id,
		Name:      name,
		Level:     level,
		MaxHP:     hp,
		CurrentHP: hp,
		Pos:       pos,
		State:     StateIdle,
	}
}
