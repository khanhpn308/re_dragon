package session

import (
	"errors"
	"sync"
	"time"
)

var (
	ErrSessionNotFound = errors.New("session not found")
)

// SessionManager manages concurrent player sessions, duplicate login eviction, and reconnect binding.
type SessionManager struct {
	mu                sync.RWMutex
	sessionsByToken   map[string]*Session
	sessionsByAccount map[string]*Session
	sessionsByConn    map[string]*Session
	defaultTTL        time.Duration
}

// NewSessionManager creates a new SessionManager with a configurable session TTL.
func NewSessionManager(defaultTTL time.Duration) *SessionManager {
	if defaultTTL <= 0 {
		defaultTTL = 30 * time.Minute
	}
	return &SessionManager{
		sessionsByToken:   make(map[string]*Session),
		sessionsByAccount: make(map[string]*Session),
		sessionsByConn:    make(map[string]*Session),
		defaultTTL:        defaultTTL,
	}
}

// CreateSession creates a session for the account, evicting any previous active session for the same account.
// Returns (newSession, evictedSession, nil).
func (sm *SessionManager) CreateSession(
	account *Account,
	roles []*Role,
	connID string,
) (*Session, *Session, error) {
	sm.mu.Lock()
	defer sm.mu.Unlock()

	var evicted *Session
	if oldSession, exists := sm.sessionsByAccount[account.Username]; exists {
		// If existing session is active, evict it
		if oldSession.State() == StateAuthenticated || oldSession.State() == StateInWorld || oldSession.State() == StateDisconnected {
			_ = oldSession.TransitionTo(StateEvicted)
			evicted = oldSession

			// Unbind old connection from conn map, but retain token in sessionsByToken marked as StateEvicted
			if oldConnID := oldSession.ConnID(); oldConnID != "" {
				delete(sm.sessionsByConn, oldConnID)
			}
		}
	}

	newSession := NewSession(account, roles, connID, sm.defaultTTL)
	sm.sessionsByToken[newSession.Token()] = newSession
	sm.sessionsByAccount[account.Username] = newSession
	if connID != "" {
		sm.sessionsByConn[connID] = newSession
	}

	return newSession, evicted, nil
}

// GetSession retrieves an active session by token, returning ErrSessionExpired if TTL has elapsed.
func (sm *SessionManager) GetSession(token string) (*Session, error) {
	sm.mu.RLock()
	defer sm.mu.RUnlock()

	s, exists := sm.sessionsByToken[token]
	if !exists {
		return nil, ErrSessionNotFound
	}

	if s.IsExpired(time.Now().UTC()) {
		return nil, ErrSessionExpired
	}

	if s.State() == StateEvicted {
		return nil, ErrSessionEvicted
	}

	return s, nil
}

// GetSessionByConn retrieves an active session bound to a specific TCP connection.
func (sm *SessionManager) GetSessionByConn(connID string) (*Session, error) {
	sm.mu.RLock()
	defer sm.mu.RUnlock()

	s, exists := sm.sessionsByConn[connID]
	if !exists {
		return nil, ErrSessionNotFound
	}

	if s.IsExpired(time.Now().UTC()) {
		return nil, ErrSessionExpired
	}

	return s, nil
}

// BindConn re-binds an existing session to a newly established TCP connection (reconnect).
func (sm *SessionManager) BindConn(token string, newConnID string) (*Session, error) {
	sm.mu.Lock()
	defer sm.mu.Unlock()

	s, exists := sm.sessionsByToken[token]
	if !exists {
		return nil, ErrSessionNotFound
	}

	now := time.Now().UTC()
	if s.IsExpired(now) {
		_ = s.TransitionTo(StateExpired)
		delete(sm.sessionsByToken, token)
		delete(sm.sessionsByAccount, s.Account().Username)
		if oldConn := s.ConnID(); oldConn != "" {
			delete(sm.sessionsByConn, oldConn)
		}
		return nil, ErrSessionExpired
	}

	if s.State() == StateEvicted {
		return nil, ErrSessionEvicted
	}

	// Unbind old connection from conn map
	if oldConn := s.ConnID(); oldConn != "" {
		delete(sm.sessionsByConn, oldConn)
	}

	// Update session connection and touch
	s.SetConnID(newConnID)
	s.Touch(now)
	sm.sessionsByConn[newConnID] = s

	// If session was disconnected, transition it back
	if s.State() == StateDisconnected {
		if s.SelectedRole() != nil {
			_ = s.TransitionTo(StateInWorld)
		} else {
			_ = s.TransitionTo(StateAuthenticated)
		}
	}

	return s, nil
}

// UnbindConn handles TCP connection drop without destroying the session, allowing reconnect within TTL.
func (sm *SessionManager) UnbindConn(connID string) {
	sm.mu.Lock()
	defer sm.mu.Unlock()

	s, exists := sm.sessionsByConn[connID]
	if !exists {
		return
	}

	delete(sm.sessionsByConn, connID)
	s.SetConnID("")

	if s.State() == StateAuthenticated || s.State() == StateInWorld {
		_ = s.TransitionTo(StateDisconnected)
	}
}

// TouchSession refreshes the activity deadline of a session.
func (sm *SessionManager) TouchSession(token string) error {
	sm.mu.RLock()
	defer sm.mu.RUnlock()

	s, exists := sm.sessionsByToken[token]
	if !exists {
		return ErrSessionNotFound
	}

	now := time.Now().UTC()
	if s.IsExpired(now) {
		return ErrSessionExpired
	}

	s.Touch(now)
	return nil
}

// CleanupExpired scans and purges all expired sessions from memory.
func (sm *SessionManager) CleanupExpired(now time.Time) int {
	sm.mu.Lock()
	defer sm.mu.Unlock()

	expiredCount := 0
	for token, s := range sm.sessionsByToken {
		if s.IsExpired(now) || s.State() == StateExpired || s.State() == StateEvicted {
			_ = s.TransitionTo(StateExpired)
			delete(sm.sessionsByToken, token)
			if acc := s.Account(); acc != nil {
				delete(sm.sessionsByAccount, acc.Username)
			}
			if connID := s.ConnID(); connID != "" {
				delete(sm.sessionsByConn, connID)
			}
			expiredCount++
		}
	}

	return expiredCount
}

// CountActive returns the number of active, non-expired sessions.
func (sm *SessionManager) CountActive() int {
	sm.mu.RLock()
	defer sm.mu.RUnlock()

	count := 0
	now := time.Now().UTC()
	for _, s := range sm.sessionsByToken {
		if !s.IsExpired(now) && s.State() != StateEvicted {
			count++
		}
	}
	return count
}
