package world

import (
	"errors"
	"sync"
	"time"
)

var (
	ErrDuplicateAction = errors.New("action already executed (idempotency key exists)")
	ErrActionInFlight  = errors.New("action with same idempotency key currently in flight")
)

type ActionStatus int

const (
	ActionPending ActionStatus = iota
	ActionCompleted
	ActionFailed
)

type ActionRecord struct {
	Key          string
	RoleID       int32
	Status       ActionStatus
	ResultCode   int32
	ErrorMessage string
	CreatedAt    time.Time
}

// IdempotencyManager tracks action nonces to prevent replay attacks and duplicate state mutations.
type IdempotencyManager struct {
	mu      sync.RWMutex
	records map[string]*ActionRecord
	ttl     time.Duration
}

// NewIdempotencyManager creates a new IdempotencyManager with configurable retention.
func NewIdempotencyManager(ttl time.Duration) *IdempotencyManager {
	if ttl <= 0 {
		ttl = 10 * time.Minute
	}
	return &IdempotencyManager{
		records: make(map[string]*ActionRecord),
		ttl:     ttl,
	}
}

// BeginAttempt checks if an action key has already been seen.
// If not seen, records it as ActionPending.
// If seen and completed, returns the cached result.
func (m *IdempotencyManager) BeginAttempt(key string, roleID int32) (*ActionRecord, error) {
	if key == "" {
		// Non-idempotent action (no key supplied)
		return nil, nil
	}

	m.mu.Lock()
	defer m.mu.Unlock()

	if rec, exists := m.records[key]; exists {
		if rec.Status == ActionPending {
			return rec, ErrActionInFlight
		}
		return rec, ErrDuplicateAction
	}

	record := &ActionRecord{
		Key:       key,
		RoleID:    roleID,
		Status:    ActionPending,
		CreatedAt: time.Now().UTC(),
	}
	m.records[key] = record
	return record, nil
}

// CompleteAttempt marks the idempotency key as completed with a result code.
func (m *IdempotencyManager) CompleteAttempt(key string, resultCode int32, errMsg string) {
	if key == "" {
		return
	}

	m.mu.Lock()
	defer m.mu.Unlock()

	if rec, exists := m.records[key]; exists {
		rec.Status = ActionCompleted
		rec.ResultCode = resultCode
		rec.ErrorMessage = errMsg
	}
}

// PurgeExpired removes old action records beyond TTL.
func (m *IdempotencyManager) PurgeExpired(now time.Time) int {
	m.mu.Lock()
	defer m.mu.Unlock()

	cutoff := now.Add(-m.ttl)
	count := 0
	for k, rec := range m.records {
		if rec.CreatedAt.Before(cutoff) {
			delete(m.records, k)
			count++
		}
	}
	return count
}
