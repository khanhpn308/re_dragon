package session

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"sync"
	"time"
)

var (
	ErrSessionExpired         = errors.New("session has expired")
	ErrSessionEvicted         = errors.New("session was evicted by duplicate login")
	ErrSessionNotActive       = errors.New("session is not in an active state")
	ErrInvalidStateTransition = errors.New("invalid session state transition")
)

type SessionState int

const (
	StateCreated SessionState = iota
	StateAuthenticated
	StateInWorld
	StateDisconnected
	StateExpired
	StateEvicted
)

func (s SessionState) String() string {
	switch s {
	case StateCreated:
		return "CREATED"
	case StateAuthenticated:
		return "AUTHENTICATED"
	case StateInWorld:
		return "IN_WORLD"
	case StateDisconnected:
		return "DISCONNECTED"
	case StateExpired:
		return "EXPIRED"
	case StateEvicted:
		return "EVICTED"
	default:
		return fmt.Sprintf("UNKNOWN(%d)", s)
	}
}

// Session tracks an authenticated player session and state machine.
type Session struct {
	mu           sync.RWMutex
	token        string
	account      *Account
	roles        []*Role
	selectedRole *Role
	connID       string
	state        SessionState
	createdAt    time.Time
	lastActiveAt time.Time
	expiresAt    time.Time
	ttl          time.Duration
}

// GenerateToken generates a cryptographically secure 32-byte hex token.
func GenerateToken() string {
	b := make([]byte, 32)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

// NewSession creates an authenticated session.
func NewSession(account *Account, roles []*Role, connID string, ttl time.Duration) *Session {
	now := time.Now().UTC()
	return &Session{
		token:        GenerateToken(),
		account:      account,
		roles:        roles,
		connID:       connID,
		state:        StateAuthenticated,
		createdAt:    now,
		lastActiveAt: now,
		expiresAt:    now.Add(ttl),
		ttl:          ttl,
	}
}

func (s *Session) Token() string {
	return s.token
}

func (s *Session) Account() *Account {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.account
}

func (s *Session) ConnID() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.connID
}

func (s *Session) SetConnID(connID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.connID = connID
}

func (s *Session) State() SessionState {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.state
}

func (s *Session) Roles() []*Role {
	s.mu.RLock()
	defer s.mu.RUnlock()
	res := make([]*Role, len(s.roles))
	copy(res, s.roles)
	return res
}

func (s *Session) SelectedRole() *Role {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.selectedRole
}

// Touch extends the session expiration deadline and updates activity timestamp.
func (s *Session) Touch(now time.Time) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.state == StateExpired || s.state == StateEvicted {
		return
	}
	s.lastActiveAt = now
	s.expiresAt = now.Add(s.ttl)
}

// IsExpired checks if the session has exceeded its lease duration.
func (s *Session) IsExpired(now time.Time) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.state == StateExpired {
		return true
	}
	return now.After(s.expiresAt)
}

// TransitionTo validates and performs state machine transitions.
func (s *Session) TransitionTo(target SessionState) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	valid := false
	switch s.state {
	case StateCreated:
		valid = (target == StateAuthenticated || target == StateExpired)
	case StateAuthenticated:
		valid = (target == StateInWorld || target == StateDisconnected || target == StateExpired || target == StateEvicted)
	case StateInWorld:
		valid = (target == StateDisconnected || target == StateExpired || target == StateEvicted)
	case StateDisconnected:
		valid = (target == StateAuthenticated || target == StateInWorld || target == StateExpired || target == StateEvicted)
	case StateExpired, StateEvicted:
		// Terminal states cannot transition to active states
		valid = false
	}

	if !valid {
		return fmt.Errorf("%w: cannot transition from %s to %s", ErrInvalidStateTransition, s.state, target)
	}

	s.state = target
	return nil
}

// SelectRole validates that the requested role ID belongs to the authenticated account and binds it.
func (s *Session) SelectRole(roleID int32) (*Role, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.state != StateAuthenticated && s.state != StateInWorld {
		return nil, fmt.Errorf("%w: session state is %s", ErrSessionNotActive, s.state)
	}

	for _, r := range s.roles {
		if r.ID == roleID {
			s.selectedRole = r
			return r, nil
		}
	}

	return nil, fmt.Errorf("%w: role ID %d is not owned by account %s", ErrUnauthorized, roleID, s.account.Username)
}
