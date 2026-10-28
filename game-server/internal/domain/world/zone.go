package world

import (
	"fmt"
	"sync"
)

// Zone represents a bounded spatial map area where players and monsters interact.
type Zone struct {
	mu       sync.RWMutex
	ID       int32
	Name     string
	players  map[int32]*PlayerEntity
	monsters map[int32]*MonsterEntity
}

func NewZone(id int32, name string) *Zone {
	return &Zone{
		ID:       id,
		Name:     name,
		players:  make(map[int32]*PlayerEntity),
		monsters: make(map[int32]*MonsterEntity),
	}
}

// AddPlayer registers a player entity in the zone.
func (z *Zone) AddPlayer(p *PlayerEntity) error {
	z.mu.Lock()
	defer z.mu.Unlock()

	if _, exists := z.players[p.RoleID]; exists {
		return fmt.Errorf("player %d already present in zone %s", p.RoleID, z.Name)
	}

	z.players[p.RoleID] = p
	return nil
}

// RemovePlayer unregisters a player from the zone.
func (z *Zone) RemovePlayer(roleID int32) {
	z.mu.Lock()
	defer z.mu.Unlock()
	delete(z.players, roleID)
}

// GetPlayer retrieves a player by role ID.
func (z *Zone) GetPlayer(roleID int32) (*PlayerEntity, bool) {
	z.mu.RLock()
	defer z.mu.RUnlock()
	p, ok := z.players[roleID]
	return p, ok
}

// PlayerCount returns the active number of players in the zone.
func (z *Zone) PlayerCount() int {
	z.mu.RLock()
	defer z.mu.RUnlock()
	return len(z.players)
}

// AddMonster registers a monster in the zone.
func (z *Zone) AddMonster(m *MonsterEntity) {
	z.mu.Lock()
	defer z.mu.Unlock()
	z.monsters[m.ID] = m
}

// GetMonster retrieves a monster by ID.
func (z *Zone) GetMonster(id int32) (*MonsterEntity, bool) {
	z.mu.RLock()
	defer z.mu.RUnlock()
	m, ok := z.monsters[id]
	return m, ok
}

// GetNearbyPlayers returns all players within radius of a target position.
func (z *Zone) GetNearbyPlayers(center Position, radius float32) []*PlayerEntity {
	z.mu.RLock()
	defer z.mu.RUnlock()

	var nearby []*PlayerEntity
	for _, p := range z.players {
		p.mu.RLock()
		dist := p.Pos.Distance(center)
		p.mu.RUnlock()

		if dist <= radius {
			nearby = append(nearby, p)
		}
	}

	return nearby
}
