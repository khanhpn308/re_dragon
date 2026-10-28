package session

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"sync"
	"time"
)

var (
	ErrInvalidCredentials = errors.New("invalid username or password")
	ErrAccountNotFound    = errors.New("account not found")
	ErrAccountExists      = errors.New("account already exists")
	ErrEmptyCredentials   = errors.New("username and password cannot be empty")
	ErrUnauthorized       = errors.New("unauthorized operation")
	ErrRoleNotFound       = errors.New("role not found")
)

// Role represents a player character associated with an account.
type Role struct {
	ID        int32  `json:"id"`
	AccountID int64  `json:"account_id"`
	Name      string `json:"name"`
	HeroCode  string `json:"hero_code"`
	Level     int16  `json:"level"`
	Gender    byte   `json:"gender"`
	Status    byte   `json:"status"`
	Vip       byte   `json:"vip"`
	Guild     string `json:"guild"`
	Online    byte   `json:"online"`
}

// Account represents an authenticated player account.
type Account struct {
	ID           int64     `json:"id"`
	Username     string    `json:"username"`
	PasswordHash string    `json:"-"`
	Salt         string    `json:"-"`
	CreatedAt    time.Time `json:"created_at"`
}

// Authenticator defines the interface for account verification and character lookup.
type Authenticator interface {
	Authenticate(ctx context.Context, username, password string) (*Account, error)
	Register(ctx context.Context, username, password string) (*Account, error)
	GetRoles(ctx context.Context, accountID int64) ([]*Role, error)
	AddRole(ctx context.Context, accountID int64, role *Role) error
}

// LocalAuthenticator provides thread-safe local/test account management without third-party coupling.
type LocalAuthenticator struct {
	mu         sync.RWMutex
	accounts   map[string]*Account // username -> account
	roles      map[int64][]*Role   // accountID -> roles
	nextAccID  int64
	nextRoleID int32
}

func hashPassword(password, salt string) string {
	h := sha256.New()
	h.Write([]byte(password + salt))
	return hex.EncodeToString(h.Sum(nil))
}

func generateSalt() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

// NewLocalAuthenticator creates and pre-seeds a local authenticator with standard test accounts.
func NewLocalAuthenticator() *LocalAuthenticator {
	auth := &LocalAuthenticator{
		accounts:   make(map[string]*Account),
		roles:      make(map[int64][]*Role),
		nextAccID:  1,
		nextRoleID: 100,
	}

	// Seed pre-approved test accounts
	ctx := context.Background()
	_, _ = auth.registerInternal(ctx, "testuser", "password123", []*Role{
		{ID: 101, Name: "SaiyanGoku", HeroCode: "10001", Level: 50, Gender: 1, Status: 0, Vip: 1, Guild: "Z-Warriors", Online: 0},
		{ID: 102, Name: "PrinceVegeta", HeroCode: "10002", Level: 48, Gender: 1, Status: 0, Vip: 2, Guild: "SaiyanPride", Online: 0},
	})
	_, _ = auth.registerInternal(ctx, "developer", "devpass456", []*Role{
		{ID: 201, Name: "UltraEgoDev", HeroCode: "10060", Level: 99, Gender: 1, Status: 0, Vip: 10, Guild: "Developers", Online: 0},
	})
	_, _ = auth.registerInternal(ctx, "reviewer", "review2026", []*Role{
		{ID: 301, Name: "AuditorGohan", HeroCode: "10005", Level: 80, Gender: 1, Status: 0, Vip: 5, Guild: "Auditors", Online: 0},
	})

	return auth
}

func (la *LocalAuthenticator) registerInternal(
	_ context.Context,
	username, password string,
	roles []*Role,
) (*Account, error) {
	if username == "" || password == "" {
		return nil, ErrEmptyCredentials
	}

	salt := generateSalt()
	acc := &Account{
		ID:           la.nextAccID,
		Username:     username,
		PasswordHash: hashPassword(password, salt),
		Salt:         salt,
		CreatedAt:    time.Now().UTC(),
	}
	la.nextAccID++
	la.accounts[username] = acc

	if len(roles) > 0 {
		for _, r := range roles {
			r.AccountID = acc.ID
		}
		la.roles[acc.ID] = roles
	} else {
		la.roles[acc.ID] = make([]*Role, 0)
	}

	return acc, nil
}

// Authenticate checks user credentials and returns the Account if valid.
func (la *LocalAuthenticator) Authenticate(_ context.Context, username, password string) (*Account, error) {
	la.mu.RLock()
	defer la.mu.RUnlock()

	acc, exists := la.accounts[username]
	if !exists {
		return nil, ErrInvalidCredentials
	}

	expectedHash := hashPassword(password, acc.Salt)
	if expectedHash != acc.PasswordHash {
		return nil, ErrInvalidCredentials
	}

	return acc, nil
}

// Register creates a new local account.
func (la *LocalAuthenticator) Register(_ context.Context, username, password string) (*Account, error) {
	la.mu.Lock()
	defer la.mu.Unlock()

	if username == "" || password == "" {
		return nil, ErrEmptyCredentials
	}

	if _, exists := la.accounts[username]; exists {
		return nil, ErrAccountExists
	}

	salt := generateSalt()
	acc := &Account{
		ID:           la.nextAccID,
		Username:     username,
		PasswordHash: hashPassword(password, salt),
		Salt:         salt,
		CreatedAt:    time.Now().UTC(),
	}
	la.nextAccID++
	la.accounts[username] = acc
	la.roles[acc.ID] = make([]*Role, 0)

	return acc, nil
}

// GetRoles returns all characters owned by the given account ID.
func (la *LocalAuthenticator) GetRoles(_ context.Context, accountID int64) ([]*Role, error) {
	la.mu.RLock()
	defer la.mu.RUnlock()

	roles, exists := la.roles[accountID]
	if !exists {
		return nil, ErrAccountNotFound
	}

	// Return a copy to avoid concurrent mutations
	res := make([]*Role, len(roles))
	copy(res, roles)
	return res, nil
}

// AddRole adds a character to an account.
func (la *LocalAuthenticator) AddRole(_ context.Context, accountID int64, role *Role) error {
	la.mu.Lock()
	defer la.mu.Unlock()

	roles, exists := la.roles[accountID]
	if !exists {
		return ErrAccountNotFound
	}

	if role.ID == 0 {
		role.ID = la.nextRoleID
		la.nextRoleID++
	}
	role.AccountID = accountID
	la.roles[accountID] = append(roles, role)
	return nil
}
