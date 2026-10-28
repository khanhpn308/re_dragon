package session

import (
	"errors"
	"testing"
	"time"
)

func TestSessionStateMachine(t *testing.T) {
	acc := &Account{ID: 1, Username: "goku"}
	roles := []*Role{
		{ID: 101, Name: "Goku", HeroCode: "10001", Level: 50},
	}
	s := NewSession(acc, roles, "conn_1", 10*time.Minute)

	if s.State() != StateAuthenticated {
		t.Fatalf("expected state %s, got %s", StateAuthenticated, s.State())
	}

	// Valid transition: Authenticated -> InWorld
	if err := s.TransitionTo(StateInWorld); err != nil {
		t.Fatalf("unexpected error transitioning to InWorld: %v", err)
	}
	if s.State() != StateInWorld {
		t.Fatalf("expected state %s, got %s", StateInWorld, s.State())
	}

	// Invalid transition: InWorld -> Authenticated
	if err := s.TransitionTo(StateAuthenticated); !errors.Is(err, ErrInvalidStateTransition) {
		t.Fatalf("expected ErrInvalidStateTransition, got %v", err)
	}

	// Valid transition: InWorld -> Disconnected
	if err := s.TransitionTo(StateDisconnected); err != nil {
		t.Fatalf("unexpected error transitioning to Disconnected: %v", err)
	}

	// Valid transition: Disconnected -> InWorld (reconnect)
	if err := s.TransitionTo(StateInWorld); err != nil {
		t.Fatalf("unexpected error reconnecting to InWorld: %v", err)
	}

	// Eviction transition: InWorld -> Evicted
	if err := s.TransitionTo(StateEvicted); err != nil {
		t.Fatalf("unexpected error evicting session: %v", err)
	}

	// Terminal state: Evicted cannot transition to any active state
	if err := s.TransitionTo(StateInWorld); !errors.Is(err, ErrInvalidStateTransition) {
		t.Fatalf("expected ErrInvalidStateTransition from terminal Evicted, got %v", err)
	}
}

func TestSessionExpirationAndPurge(t *testing.T) {
	sm := NewSessionManager(50 * time.Millisecond)
	acc := &Account{ID: 2, Username: "vegeta"}
	roles := []*Role{
		{ID: 102, Name: "Vegeta", HeroCode: "10002", Level: 48},
	}

	s, _, err := sm.CreateSession(acc, roles, "conn_2")
	if err != nil {
		t.Fatalf("failed to create session: %v", err)
	}

	// Immediately after creation, session should be active
	retrieved, err := sm.GetSession(s.Token())
	if err != nil {
		t.Fatalf("failed to retrieve session: %v", err)
	}
	if retrieved.Token() != s.Token() {
		t.Fatalf("token mismatch")
	}

	// Wait for TTL to elapse
	time.Sleep(60 * time.Millisecond)

	// Session should now be expired
	if _, err := sm.GetSession(s.Token()); !errors.Is(err, ErrSessionExpired) {
		t.Fatalf("expected ErrSessionExpired, got %v", err)
	}

	// Cleanup should purge the expired session
	purged := sm.CleanupExpired(time.Now().UTC())
	if purged != 1 {
		t.Fatalf("expected 1 purged session, got %d", purged)
	}

	// Should now be ErrSessionNotFound
	if _, err := sm.GetSession(s.Token()); !errors.Is(err, ErrSessionNotFound) {
		t.Fatalf("expected ErrSessionNotFound after cleanup, got %v", err)
	}
}

func TestSessionTouch(t *testing.T) {
	sm := NewSessionManager(80 * time.Millisecond)
	acc := &Account{ID: 3, Username: "piccolo"}
	s, _, err := sm.CreateSession(acc, nil, "conn_3")
	if err != nil {
		t.Fatalf("create session error: %v", err)
	}

	// Sleep 50ms, touch session, sleep another 50ms -> should NOT expire (total 100ms > 80ms)
	time.Sleep(50 * time.Millisecond)
	if err := sm.TouchSession(s.Token()); err != nil {
		t.Fatalf("touch session error: %v", err)
	}

	time.Sleep(50 * time.Millisecond)
	if _, err := sm.GetSession(s.Token()); err != nil {
		t.Fatalf("session expired prematurely despite touch: %v", err)
	}
}

func TestDuplicateLoginEviction(t *testing.T) {
	sm := NewSessionManager(10 * time.Minute)
	acc := &Account{ID: 4, Username: "gohan"}
	roles := []*Role{
		{ID: 301, Name: "Gohan", HeroCode: "10005", Level: 80},
	}

	// First login on socket 1
	sess1, evicted0, err := sm.CreateSession(acc, roles, "conn_socket_1")
	if err != nil {
		t.Fatalf("failed to create initial session: %v", err)
	}
	if evicted0 != nil {
		t.Fatalf("expected no evicted session on initial login")
	}

	// Second login for same account on socket 2
	sess2, evicted1, err := sm.CreateSession(acc, roles, "conn_socket_2")
	if err != nil {
		t.Fatalf("failed to create second session: %v", err)
	}

	if evicted1 == nil {
		t.Fatalf("expected previous session to be returned as evicted")
	}
	if evicted1.Token() != sess1.Token() {
		t.Fatalf("evicted session token mismatch")
	}
	if evicted1.State() != StateEvicted {
		t.Fatalf("expected evicted session state to be %s, got %s", StateEvicted, evicted1.State())
	}

	// Accessing old session token must return ErrSessionEvicted
	if _, err := sm.GetSession(sess1.Token()); !errors.Is(err, ErrSessionEvicted) {
		t.Fatalf("expected ErrSessionEvicted for old session, got %v", err)
	}

	// New session must be active
	active, err := sm.GetSession(sess2.Token())
	if err != nil {
		t.Fatalf("failed to retrieve active new session: %v", err)
	}
	if active.ConnID() != "conn_socket_2" {
		t.Fatalf("expected new conn ID conn_socket_2, got %s", active.ConnID())
	}
}

func TestReconnectBinding(t *testing.T) {
	sm := NewSessionManager(10 * time.Minute)
	acc := &Account{ID: 5, Username: "trunks"}
	roles := []*Role{
		{ID: 501, Name: "Trunks", HeroCode: "10008", Level: 45},
	}

	sess, _, _ := sm.CreateSession(acc, roles, "conn_original")
	_, _ = sess.SelectRole(501)
	_ = sess.TransitionTo(StateInWorld)

	// Network drop: socket disconnects
	sm.UnbindConn("conn_original")
	if sess.State() != StateDisconnected {
		t.Fatalf("expected StateDisconnected after unbind, got %s", sess.State())
	}
	if sess.ConnID() != "" {
		t.Fatalf("expected empty connID after unbind, got %s", sess.ConnID())
	}

	// Reconnect on new socket
	rebound, err := sm.BindConn(sess.Token(), "conn_reconnected")
	if err != nil {
		t.Fatalf("failed to bind reconnecting socket: %v", err)
	}

	if rebound.State() != StateInWorld {
		t.Fatalf("expected rebound session to restore StateInWorld, got %s", rebound.State())
	}
	if rebound.ConnID() != "conn_reconnected" {
		t.Fatalf("expected connID conn_reconnected, got %s", rebound.ConnID())
	}

	byConn, err := sm.GetSessionByConn("conn_reconnected")
	if err != nil || byConn.Token() != sess.Token() {
		t.Fatalf("failed to lookup session by new connection ID")
	}
}

func TestServerSideRoleAuthorization(t *testing.T) {
	accGoku := &Account{ID: 10, Username: "goku"}
	rolesGoku := []*Role{
		{ID: 101, Name: "Goku", HeroCode: "10001", Level: 50},
		{ID: 102, Name: "Kakarot", HeroCode: "10001", Level: 52},
	}

	sess := NewSession(accGoku, rolesGoku, "conn_auth_test", 10*time.Minute)

	// Valid owned role selection
	r1, err := sess.SelectRole(101)
	if err != nil {
		t.Fatalf("unexpected error selecting owned role: %v", err)
	}
	if r1.Name != "Goku" {
		t.Fatalf("expected Goku, got %s", r1.Name)
	}

	// Unauthorized role selection: role ID 999 not in account's role list
	rBad, err := sess.SelectRole(999)
	if err == nil {
		t.Fatalf("expected error selecting unowned role, got role: %+v", rBad)
	}
	if !errors.Is(err, ErrUnauthorized) {
		t.Fatalf("expected ErrUnauthorized, got %v", err)
	}
}
