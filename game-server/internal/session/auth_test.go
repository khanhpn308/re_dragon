package session

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"
)

func TestLocalAuthenticatorPreseededAccounts(t *testing.T) {
	auth := NewLocalAuthenticator()
	ctx := context.Background()

	// 1. Test testuser
	acc1, err := auth.Authenticate(ctx, "testuser", "password123")
	if err != nil {
		t.Fatalf("failed to authenticate preseeded testuser: %v", err)
	}
	if acc1.Username != "testuser" {
		t.Fatalf("expected testuser, got %s", acc1.Username)
	}

	roles1, err := auth.GetRoles(ctx, acc1.ID)
	if err != nil || len(roles1) != 2 {
		t.Fatalf("expected 2 roles for testuser, got %d, err: %v", len(roles1), err)
	}

	// 2. Test developer
	acc2, err := auth.Authenticate(ctx, "developer", "devpass456")
	if err != nil {
		t.Fatalf("failed to authenticate preseeded developer: %v", err)
	}
	roles2, err := auth.GetRoles(ctx, acc2.ID)
	if err != nil || len(roles2) != 1 || roles2[0].HeroCode != "10060" {
		t.Fatalf("expected Ultra Ego hero 10060 for developer, got %+v", roles2)
	}

	// 3. Test reviewer
	acc3, err := auth.Authenticate(ctx, "reviewer", "review2026")
	if err != nil {
		t.Fatalf("failed to authenticate preseeded reviewer: %v", err)
	}
	roles3, err := auth.GetRoles(ctx, acc3.ID)
	if err != nil || len(roles3) != 1 {
		t.Fatalf("expected 1 role for reviewer, got %d", len(roles3))
	}
}

func TestLocalAuthenticatorNegativeCases(t *testing.T) {
	auth := NewLocalAuthenticator()
	ctx := context.Background()

	// 1. Bad password
	if _, err := auth.Authenticate(ctx, "testuser", "wrongpassword"); !errors.Is(err, ErrInvalidCredentials) {
		t.Fatalf("expected ErrInvalidCredentials for wrong password, got %v", err)
	}

	// 2. Non-existent account
	if _, err := auth.Authenticate(ctx, "nonexistent", "somepassword"); !errors.Is(err, ErrInvalidCredentials) {
		t.Fatalf("expected ErrInvalidCredentials for nonexistent account, got %v", err)
	}

	// 3. Empty credentials
	if _, err := auth.Authenticate(ctx, "", ""); !errors.Is(err, ErrInvalidCredentials) {
		t.Fatalf("expected ErrInvalidCredentials for empty strings, got %v", err)
	}

	// 4. Empty registration
	if _, err := auth.Register(ctx, "", "somepass"); !errors.Is(err, ErrEmptyCredentials) {
		t.Fatalf("expected ErrEmptyCredentials for registration without username, got %v", err)
	}
}

func TestLocalAuthenticatorRegistration(t *testing.T) {
	auth := NewLocalAuthenticator()
	ctx := context.Background()

	// Valid registration
	newAcc, err := auth.Register(ctx, "newplayer", "playerpass789")
	if err != nil {
		t.Fatalf("failed to register new account: %v", err)
	}
	if newAcc.Username != "newplayer" {
		t.Fatalf("expected newplayer username, got %s", newAcc.Username)
	}

	// Immediate successful auth
	authed, err := auth.Authenticate(ctx, "newplayer", "playerpass789")
	if err != nil || authed.ID != newAcc.ID {
		t.Fatalf("failed to authenticate newly registered account: %v", err)
	}

	// Duplicate registration must fail with ErrAccountExists
	if _, err := auth.Register(ctx, "newplayer", "anotherpass"); !errors.Is(err, ErrAccountExists) {
		t.Fatalf("expected ErrAccountExists for duplicate username, got %v", err)
	}

	// Add role to new account
	err = auth.AddRole(ctx, newAcc.ID, &Role{
		Name:     "NewWarrior",
		HeroCode: "10003",
		Level:    1,
	})
	if err != nil {
		t.Fatalf("failed to add role: %v", err)
	}

	roles, err := auth.GetRoles(ctx, newAcc.ID)
	if err != nil || len(roles) != 1 || roles[0].Name != "NewWarrior" {
		t.Fatalf("failed to verify added role: %+v", roles)
	}
}

func TestLocalAuthenticatorConcurrentAccess(t *testing.T) {
	auth := NewLocalAuthenticator()
	ctx := context.Background()

	const workers = 50
	var wg sync.WaitGroup
	wg.Add(workers * 2)

	// Concurrent authentications
	for i := 0; i < workers; i++ {
		go func() {
			defer wg.Done()
			for j := 0; j < 20; j++ {
				_, _ = auth.Authenticate(ctx, "testuser", "password123")
				_, _ = auth.Authenticate(ctx, "testuser", "wrongpass")
			}
		}()
	}

	// Concurrent registrations
	for i := 0; i < workers; i++ {
		workerID := i
		go func() {
			defer wg.Done()
			uname := fmt.Sprintf("user_worker_%d", workerID)
			_, _ = auth.Register(ctx, uname, "pass123")
			_, _ = auth.Authenticate(ctx, uname, "pass123")
		}()
	}

	wg.Wait()
}
