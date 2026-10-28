package postgres

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"returnsaiyan/gameserver/internal/domain/hero"
)

// HeroOnboardingRepository is a persistence foundation; not an implemented
// client wire protocol. Do not invoke before verified cost, eligibility and S2C.
type HeroOnboardingRepository struct{ pool *pgxpool.Pool }

func NewHeroOnboardingRepository(pool *pgxpool.Pool) *HeroOnboardingRepository {
	return &HeroOnboardingRepository{pool: pool}
}

// RecordAuthorizedSummon commits one approved outcome once per request ID.
// This function deliberately does not charge currency; do NOT call it as a
// paid summon until an atomic currency-debit contract has been implemented.
func (r *HeroOnboardingRepository) RecordAuthorizedSummon(
	ctx context.Context, accountID int64, requestID string, heroCode int32, aptitude int,
) (instanceID int64, err error) {
	if r == nil || r.pool == nil {
		return 0, errors.New("missing pool")
	}
	if accountID <= 0 || requestID == "" || len(requestID) > 128 || heroCode <= 0 {
		return 0, errors.New("invalid summon parameters")
	}
	if err = hero.ValidateHeroProgression(1, 0, aptitude); err != nil {
		return 0, err
	}
	err = WithTx(ctx, r.pool, pgx.TxOptions{}, func(tx pgx.Tx) error {
		var reserved string
		e := tx.QueryRow(ctx, `
   INSERT INTO hero_summon_operations(account_id,request_id,mode,hero_code)
   VALUES($1,$2,'EARTH_X1',$3)
   ON CONFLICT(account_id,request_id) DO NOTHING RETURNING request_id`,
			accountID, requestID, heroCode).Scan(&reserved)
		if errors.Is(e, pgx.ErrNoRows) {
			var previousCode int32
			e = tx.QueryRow(ctx, `SELECT hero_instance_id,hero_code
    FROM hero_summon_operations WHERE account_id=$1 AND request_id=$2`,
				accountID, requestID).Scan(&instanceID, &previousCode)
			if e != nil {
				return fmt.Errorf("replay lookup: %w", e)
			}
			if previousCode != heroCode {
				return errors.New("summon request ID reused with another hero")
			}
			return nil
		}
		if e != nil {
			return fmt.Errorf("reserve summon ID: %w", e)
		}
		e = tx.QueryRow(ctx, `INSERT INTO hero_instances
   (account_id,hero_code,aptitude,level,promotion_tier,acquired_via)
   VALUES($1,$2,$3,1,0,'EARTH_X1') RETURNING id`,
			accountID, heroCode, aptitude).Scan(&instanceID)
		if e != nil {
			return fmt.Errorf("insert hero: %w", e)
		}
		_, e = tx.Exec(ctx, `UPDATE hero_summon_operations SET hero_instance_id=$3
   WHERE account_id=$1 AND request_id=$2`, accountID, requestID, instanceID)
		return e
	})
	if err != nil {
		return 0, err
	}
	return instanceID, nil
}

// AssignActiveSlot validates ownership; distinct from equipment and reserve.
func (r *HeroOnboardingRepository) AssignActiveSlot(
	ctx context.Context, accountID int64, slot int, instanceID int64,
) error {
	if r == nil || r.pool == nil {
		return errors.New("missing pool")
	}
	if accountID <= 0 || instanceID <= 0 {
		return errors.New("invalid account or hero instance")
	}
	if err := hero.ValidateActiveFormationSlot(slot); err != nil {
		return err
	}
	return WithTx(ctx, r.pool, pgx.TxOptions{}, func(tx pgx.Tx) error {
		var exists bool
		if err := tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM hero_instances
   WHERE account_id=$1 AND id=$2)`, accountID, instanceID).Scan(&exists); err != nil {
			return err
		}
		if !exists {
			return errors.New("hero not owned by account")
		}
		var oldSlot int
		err := tx.QueryRow(ctx, `SELECT slot FROM hero_formations
   WHERE account_id=$1 AND hero_instance_id=$2 FOR UPDATE`, accountID, instanceID).Scan(&oldSlot)
		if err != nil && !errors.Is(err, pgx.ErrNoRows) {
			return err
		}
		if err == nil && oldSlot != slot {
			return errors.New("hero already assigned")
		}
		_, err = tx.Exec(ctx, `INSERT INTO hero_formations(account_id,slot,hero_instance_id)
   VALUES($1,$2,$3) ON CONFLICT(account_id,slot)
   DO UPDATE SET hero_instance_id=EXCLUDED.hero_instance_id,updated_at=NOW()`,
			accountID, slot, instanceID)
		return err
	})
}
