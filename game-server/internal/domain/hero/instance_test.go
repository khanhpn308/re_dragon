package hero

import (
 "bytes"
 "testing"
)
func TestHeroProgressionBoundaries(t *testing.T) {
 for _,tc:=range []struct{lv,promo,apt int;ok bool}{
  {1,0,0,true},{200,40,123,true},{0,0,0,false},{201,0,0,false},
  {1,-1,0,false},{1,41,0,false},{1,0,-1,false},
 } {
  err:=ValidateHeroProgression(tc.lv,tc.promo,tc.apt)
  if (err==nil)!=tc.ok {t.Fatalf("%+v -> %v",tc,err)}
 }
}
func TestActiveFormationSlots(t *testing.T) {
 for i:=-1;i<=6;i++ {
  err:=ValidateActiveFormationSlot(i)
  if (err==nil)!=(i>=1&&i<=4) {t.Fatalf("slot %d: %v",i,err)}
 }
}
func TestDrawEligible(t *testing.T) {
  got,err:=DrawEligible(bytes.NewReader(make([]byte,32)),[]int32{10001})
  if err!=nil||got!=10001 {t.Fatalf("%v %v",got,err)}
  if _,err=DrawEligible(nil,[]int32{10001});err==nil {t.Fatal("accepted nil RNG")}
  if _,err=DrawEligible(bytes.NewReader(make([]byte,4)),nil);err==nil {t.Fatal("accepted empty pool")}
}
