package hero

import (
	"errors"
	"sync"
	"testing"

	"returnsaiyan/gameserver/internal/session"
)

func TestCanonical142HeroAccounting(t *testing.T) {
	reg := NewCanonicalRegistry()

	all := reg.ListAll()
	if len(all) != 142 {
		t.Fatalf("expected 142 canonical heroes, got %d", len(all))
	}

	baseline := reg.ListBaseline()
	if len(baseline) != 128 {
		t.Fatalf("expected 128 baseline heroes, got %d", len(baseline))
	}

	donors := reg.ListDonorAdditions()
	if len(donors) != 14 {
		t.Fatalf("expected 14 donor hero additions, got %d", len(donors))
	}

	// Verify no ID collisions
	seenIDs := make(map[int32]string)
	for _, h := range all {
		if prevName, exists := seenIDs[h.ID]; exists {
			t.Fatalf("duplicate canonical hero ID %d detected between %q and %q", h.ID, prevName, h.Name)
		}
		seenIDs[h.ID] = h.Name
	}
}

func TestReturnSaiyanCustomHeroesPreserved(t *testing.T) {
	reg := NewCanonicalRegistry()

	// 10060: Ultra Ego Vegeta
	h10060, err := reg.Get(10060)
	if err != nil {
		t.Fatalf("failed to find custom hero 10060: %v", err)
	}
	if h10060.Name != "Ultra Ego Vegeta" {
		t.Fatalf("expected Ultra Ego Vegeta, got %s", h10060.Name)
	}
	if h10060.ServerGated {
		t.Fatalf("ReturnSaiyan custom hero 10060 must not be SERVER_GATED")
	}

	// 10063: Legendary Broly (Fury)
	h10063, err := reg.Get(10063)
	if err != nil {
		t.Fatalf("failed to find custom hero 10063: %v", err)
	}
	if h10063.Name != "Legendary Broly (Fury)" {
		t.Fatalf("expected Legendary Broly (Fury), got %s", h10063.Name)
	}
	if h10063.ServerGated {
		t.Fatalf("ReturnSaiyan custom hero 10063 must not be SERVER_GATED")
	}

	// 10064: Black Frieza
	h10064, err := reg.Get(10064)
	if err != nil {
		t.Fatalf("failed to find custom hero 10064: %v", err)
	}
	if h10064.Name != "Black Frieza" {
		t.Fatalf("expected Black Frieza, got %s", h10064.Name)
	}
	if h10064.ServerGated {
		t.Fatalf("ReturnSaiyan custom hero 10064 must not be SERVER_GATED")
	}
}

func TestDonorHeroAdditionsServerGated(t *testing.T) {
	reg := NewCanonicalRegistry()

	expectedDonors := []struct {
		id   int32
		name string
	}{
		{10081, "Hit"},
		{10082, "Android 21"},
		{10083, "Super Saiyan 4 Gogeta"},
		{10062, "Vados"},
		{10084, "Towa"},
		{10085, "Toppo"},
		{10065, "Jiren"},
		{10066, "Shin"},
		{10067, "DC Majin Vegeta "},
		{10068, "DC Super Saiyan 3 "},
		{10069, "Super Saiyan Blue Vegito"},
		{10070, "Arale"},
		{90038, "Hit Doppelganger"},
		{90037, "Toppo"},
	}

	for _, ed := range expectedDonors {
		h, err := reg.Get(ed.id)
		if err != nil {
			t.Fatalf("missing donor hero ID %d (%s): %v", ed.id, ed.name, err)
		}
		if !h.ServerGated {
			t.Fatalf("donor hero ID %d (%s) must be SERVER_GATED", ed.id, ed.name)
		}
		if h.Classification != ClassDonorAddition {
			t.Fatalf("donor hero ID %d expected ClassDonorAddition, got %s", ed.id, h.Classification)
		}
	}
}

func TestSelectionValidation(t *testing.T) {
	reg := NewCanonicalRegistry()

	// 1. Baseline hero (Young Goku 10001) - allowed without entitlement
	h1, err := reg.ValidateSelection(10001, false)
	if err != nil {
		t.Fatalf("baseline hero selection failed: %v", err)
	}
	if h1.Name != "Young Goku" {
		t.Fatalf("expected Young Goku, got %s", h1.Name)
	}

	// 2. Custom ReturnSaiyan hero (Ultra Ego Vegeta 10060) - allowed without entitlement
	h2, err := reg.ValidateSelection(10060, false)
	if err != nil {
		t.Fatalf("custom ReturnSaiyan hero selection failed: %v", err)
	}
	if h2.Name != "Ultra Ego Vegeta" {
		t.Fatalf("expected Ultra Ego Vegeta, got %s", h2.Name)
	}

	// 3. Donor hero (Android 21 10082) - unentitled must be rejected
	if _, err := reg.ValidateSelection(10082, false); !errors.Is(err, ErrHeroServerGated) {
		t.Fatalf("expected ErrHeroServerGated for unentitled donor selection, got %v", err)
	}

	// 4. Donor hero (Android 21 10082) - entitled must succeed
	h4, err := reg.ValidateSelection(10082, true)
	if err != nil {
		t.Fatalf("entitled donor selection failed: %v", err)
	}
	if h4.Name != "Android 21" {
		t.Fatalf("expected Android 21, got %s", h4.Name)
	}

	// 5. Invalid hero ID - rejected with ErrHeroNotFound
	if _, err := reg.ValidateSelection(99999, true); !errors.Is(err, ErrHeroNotFound) {
		t.Fatalf("expected ErrHeroNotFound, got %v", err)
	}
}

func TestRosterServiceCharacterCreation(t *testing.T) {
	svc := NewRosterService(nil)
	acc := &session.Account{ID: 10, Username: "testuser"}

	// 1. Create character with standard baseline hero (10001)
	r1, err := svc.CreateRoleForAccount(acc, "MyGoku", 10001)
	if err != nil {
		t.Fatalf("failed to create character with baseline hero: %v", err)
	}
	if r1.Name != "MyGoku" || r1.HeroCode != "10001" {
		t.Fatalf("character profile mismatch: %+v", r1)
	}

	// 2. Attempt to create character with locked donor hero (10081 - Hit)
	if _, err := svc.CreateRoleForAccount(acc, "MyHit", 10081); !errors.Is(err, ErrHeroServerGated) {
		t.Fatalf("expected ErrHeroServerGated for unentitled donor hero creation, got %v", err)
	}

	// 3. Grant unlock for donor hero 10081
	if err := svc.GrantDonorEntitlement(acc.Username, 10081); err != nil {
		t.Fatalf("failed to grant donor entitlement: %v", err)
	}

	// 4. Now create character with donor hero 10081 -> must succeed
	r2, err := svc.CreateRoleForAccount(acc, "MyHit", 10081)
	if err != nil {
		t.Fatalf("character creation failed after unlock: %v", err)
	}
	if r2.Name != "MyHit" || r2.HeroCode != "10081" {
		t.Fatalf("character profile mismatch: %+v", r2)
	}

	// 5. Revoke unlock and verify subsequent creation is blocked
	_ = svc.RevokeDonorEntitlement(acc.Username, 10081)
	if _, err := svc.CreateRoleForAccount(acc, "AnotherHit", 10081); !errors.Is(err, ErrHeroServerGated) {
		t.Fatalf("expected ErrHeroServerGated after entitlement revoke, got %v", err)
	}
}

func TestConcurrentRosterOperations(t *testing.T) {
	svc := NewRosterService(nil)
	acc := &session.Account{ID: 20, Username: "concurrent_player"}

	const workers = 30
	var wg sync.WaitGroup
	wg.Add(workers * 2)

	// Concurrently query and create baseline characters
	for i := 0; i < workers; i++ {
		go func(idx int) {
			defer wg.Done()
			_, _ = svc.CreateRoleForAccount(acc, "Char", 10001)
			_, _ = svc.CreateRoleForAccount(acc, "CharCustom", 10060)
		}(i)
	}

	// Concurrently grant/revoke donor entitlements
	for i := 0; i < workers; i++ {
		go func(idx int) {
			defer wg.Done()
			_ = svc.GrantDonorEntitlement(acc.Username, 10082)
			_, _ = svc.CreateRoleForAccount(acc, "Android21", 10082)
			_ = svc.RevokeDonorEntitlement(acc.Username, 10082)
		}(i)
	}

	wg.Wait()
}
