package hero

import (
	"errors"
	"fmt"
	"sync"
)

var (
	ErrHeroNotFound    = errors.New("hero ID not found in canonical union")
	ErrHeroServerGated = errors.New("hero is server-gated and requires explicit server entitlement")
	ErrHeroIDCollision = errors.New("hero ID collision detected")
)

// HeroClassification indicates whether a hero is shared, ReturnSaiyan custom, or donor addition.
type HeroClassification string

const (
	ClassShared             HeroClassification = "SHARED_HERO"
	ClassCustomReturnSaiyan HeroClassification = "CUSTOM_RETURN_SAIYAN"
	ClassDonorAddition      HeroClassification = "DONOR_ADDITION"
)

// HeroDefinition represents a canonical unified hero row from G2/G3.
type HeroDefinition struct {
	ID                  int32              `json:"id"`
	Name                string             `json:"name"`
	Classification      HeroClassification `json:"classification"`
	ServerGated         bool               `json:"server_gated"`
	SourceA_ID          int32              `json:"source_a_id"`
	SourceB_ID          int32              `json:"source_b_id"`
	CollisionResolution string             `json:"collision_resolution"`
	TextureRef          string             `json:"texture_ref"`
	SkeletonRef         string             `json:"skeleton_ref"`
	AnimationRef        string             `json:"animation_ref"`
}

// CanonicalRegistry manages the frozen 142-hero canonical catalog from G2/G3.
type CanonicalRegistry struct {
	mu             sync.RWMutex
	heroesByID     map[int32]*HeroDefinition
	allHeroes      []*HeroDefinition
	baselineHeroes []*HeroDefinition
	donorAdditions []*HeroDefinition
}

// DefaultRegistry is the singleton canonical registry instance initialized with all 142 heroes.
var DefaultRegistry = NewCanonicalRegistry()

// NewCanonicalRegistry constructs and indexes the 142 canonical heroes.
func NewCanonicalRegistry() *CanonicalRegistry {
	reg := &CanonicalRegistry{
		heroesByID:     make(map[int32]*HeroDefinition, len(RawCanonicalCatalog)),
		allHeroes:      make([]*HeroDefinition, 0, len(RawCanonicalCatalog)),
		baselineHeroes: make([]*HeroDefinition, 0, 128),
		donorAdditions: make([]*HeroDefinition, 0, 14),
	}

	for _, h := range RawCanonicalCatalog {
		reg.heroesByID[h.ID] = h
		reg.allHeroes = append(reg.allHeroes, h)

		if h.Classification == ClassDonorAddition || h.ServerGated {
			reg.donorAdditions = append(reg.donorAdditions, h)
		} else {
			reg.baselineHeroes = append(reg.baselineHeroes, h)
		}
	}

	return reg
}

// Get returns the hero definition by canonical ID.
func (r *CanonicalRegistry) Get(id int32) (*HeroDefinition, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	h, exists := r.heroesByID[id]
	if !exists {
		return nil, fmt.Errorf("%w: ID %d", ErrHeroNotFound, id)
	}
	return h, nil
}

// ListAll returns all 142 canonical heroes.
func (r *CanonicalRegistry) ListAll() []*HeroDefinition {
	r.mu.RLock()
	defer r.mu.RUnlock()
	res := make([]*HeroDefinition, len(r.allHeroes))
	copy(res, r.allHeroes)
	return res
}

// ListBaseline returns the 128 ReturnSaiyan baseline heroes (including custom 10060, 10063, 10064).
func (r *CanonicalRegistry) ListBaseline() []*HeroDefinition {
	r.mu.RLock()
	defer r.mu.RUnlock()
	res := make([]*HeroDefinition, len(r.baselineHeroes))
	copy(res, r.baselineHeroes)
	return res
}

// ListDonorAdditions returns the 14 Global donor hero additions.
func (r *CanonicalRegistry) ListDonorAdditions() []*HeroDefinition {
	r.mu.RLock()
	defer r.mu.RUnlock()
	res := make([]*HeroDefinition, len(r.donorAdditions))
	copy(res, r.donorAdditions)
	return res
}

// ValidateSelection verifies that a hero selection is valid and compliant with SERVER_GATED entitlements.
func (r *CanonicalRegistry) ValidateSelection(heroID int32, isEntitled bool) (*HeroDefinition, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	h, exists := r.heroesByID[heroID]
	if !exists {
		return nil, fmt.Errorf("%w: ID %d", ErrHeroNotFound, heroID)
	}

	if h.ServerGated && !isEntitled {
		return nil, fmt.Errorf("%w: hero %d (%s) is SERVER_GATED and requires server entitlement", ErrHeroServerGated, h.ID, h.Name)
	}

	return h, nil
}
