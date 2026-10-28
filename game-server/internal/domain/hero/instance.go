package hero

import (
 "crypto/rand"
 "errors"
 "fmt"
 "io"
 "math/big"
)

type OwnedInstance struct {
 ID int64
 AccountID int64
 HeroCode int32
 Aptitude int
 Level int
 PromotionTier int
 CombatPower *int64 // nil until a source-grounded formula is approved
}

func ValidateHeroProgression(level, promotionTier, aptitude int) error {
 if level<1 || level>200 {return fmt.Errorf("hero level %d outside 1..200",level)}
 if promotionTier<0 || promotionTier>40 {return fmt.Errorf("promotion tier %d outside 0..40",promotionTier)}
 if aptitude<0 {return errors.New("negative hero aptitude")}
 return nil
}
func ValidateActiveFormationSlot(slot int) error {
 if slot<1 || slot>4 {return fmt.Errorf("active formation slot %d outside 1..4",slot)}
 return nil
}

// Only call with an explicitly approved eligible pool. Uniform selection is
// a test policy, not a claim about the original game's drop distribution.
func DrawEligible(reader io.Reader, eligible []int32) (int32,error) {
 if reader==nil || len(eligible)==0 {return 0,errors.New("missing RNG or approved eligible pool")}
 i,err:=rand.Int(reader,big.NewInt(int64(len(eligible))))
 if err!=nil {return 0,fmt.Errorf("secure draw: %w",err)}
 return eligible[int(i.Int64())],nil
}
