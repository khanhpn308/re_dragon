package hero

import (
	"fmt"
	"sync"

	"returnsaiyan/gameserver/internal/session"
)

// AccountRoster tracks hero unlock entitlements for an account.
type AccountRoster struct {
	mu               sync.RWMutex
	Username         string         `json:"username"`
	UnlockedGatedIDs map[int32]bool `json:"unlocked_gated_ids"`
}

// NewAccountRoster creates a new roster for an account.
func NewAccountRoster(username string) *AccountRoster {
	return &AccountRoster{
		Username:         username,
		UnlockedGatedIDs: make(map[int32]bool),
	}
}

// IsEntitled returns true if the hero is non-gated or explicitly unlocked.
func (ar *AccountRoster) IsEntitled(heroDef *HeroDefinition) bool {
	if !heroDef.ServerGated {
		return true
	}
	ar.mu.RLock()
	defer ar.mu.RUnlock()
	return ar.UnlockedGatedIDs[heroDef.ID]
}

// GrantUnlock unlocks a server-gated donor hero for this account.
func (ar *AccountRoster) GrantUnlock(heroID int32) {
	ar.mu.Lock()
	defer ar.mu.Unlock()
	ar.UnlockedGatedIDs[heroID] = true
}

// RevokeUnlock removes entitlement for a server-gated hero.
func (ar *AccountRoster) RevokeUnlock(heroID int32) {
	ar.mu.Lock()
	defer ar.mu.Unlock()
	delete(ar.UnlockedGatedIDs, heroID)
}

// RosterService manages account hero roster states, donor entitlements, and character creation.
type RosterService struct {
	mu       sync.RWMutex
	registry *CanonicalRegistry
	rosters  map[string]*AccountRoster
}

// NewRosterService creates a new RosterService backed by the given canonical registry.
func NewRosterService(registry *CanonicalRegistry) *RosterService {
	if registry == nil {
		registry = DefaultRegistry
	}
	return &RosterService{
		registry: registry,
		rosters:  make(map[string]*AccountRoster),
	}
}

// GetOrCreateRoster retrieves or creates an AccountRoster for the given username.
func (s *RosterService) GetOrCreateRoster(username string) *AccountRoster {
	s.mu.Lock()
	defer s.mu.Unlock()

	r, exists := s.rosters[username]
	if !exists {
		r = NewAccountRoster(username)
		s.rosters[username] = r
	}
	return r
}

// GrantDonorEntitlement grants server-side unlock for a SERVER_GATED donor hero.
func (s *RosterService) GrantDonorEntitlement(username string, heroID int32) error {
	heroDef, err := s.registry.Get(heroID)
	if err != nil {
		return err
	}

	if !heroDef.ServerGated {
		// Non-gated baseline heroes are accessible by default without explicit unlock
		return nil
	}

	roster := s.GetOrCreateRoster(username)
	roster.GrantUnlock(heroID)
	return nil
}

// RevokeDonorEntitlement revokes server-side entitlement for a donor hero.
func (s *RosterService) RevokeDonorEntitlement(username string, heroID int32) error {
	roster := s.GetOrCreateRoster(username)
	roster.RevokeUnlock(heroID)
	return nil
}

// CreateRoleForAccount validates hero selection and constructs a new player character role.
func (s *RosterService) CreateRoleForAccount(
	acc *session.Account,
	roleName string,
	heroID int32,
) (*session.Role, error) {
	if acc == nil {
		return nil, session.ErrAccountNotFound
	}
	if roleName == "" {
		return nil, fmt.Errorf("role name cannot be empty")
	}

	roster := s.GetOrCreateRoster(acc.Username)
	heroDef, err := s.registry.Get(heroID)
	if err != nil {
		return nil, err
	}

	isEntitled := roster.IsEntitled(heroDef)
	if _, err := s.registry.ValidateSelection(heroID, isEntitled); err != nil {
		return nil, err
	}

	role := &session.Role{
		AccountID: acc.ID,
		Name:      roleName,
		HeroCode:  fmt.Sprintf("%d", heroID),
		Level:     1,
		Gender:    1,
		Status:    0,
		Vip:       0,
		Guild:     "",
		Online:    0,
	}

	return role, nil
}
