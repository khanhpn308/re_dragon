package protocol

import (
	"encoding/hex"
	"encoding/json"
	"os"
	"testing"
)

type GoldenVectors struct {
	KeyDerivationVectors []struct {
		SeedHex       string `json:"seed_hex"`
		GreetingHex   string `json:"greeting_hex"`
		DerivedKeyHex string `json:"derived_key_hex"`
		DerivedKeyDec int    `json:"derived_key_dec"`
	} `json:"key_derivation_vectors"`
	C2SFramingVectors []struct {
		SeedHex        string `json:"seed_hex"`
		KeyHex         string `json:"key_hex"`
		Seq            int    `json:"seq"`
		OpcodeHex      string `json:"opcode_hex"`
		UnencryptedHex string `json:"unencrypted_hex"`
		EncryptedHex   string `json:"encrypted_hex"`
		TotalLen       int    `json:"total_len"`
	} `json:"c2s_framing_vectors"`
	S2CFramingVectors []struct {
		SeedHex           string `json:"seed_hex"`
		KeyHex            string `json:"key_hex"`
		OpcodeHex         string `json:"opcode_hex"`
		PayloadHex        string `json:"payload_hex"`
		EncryptedFrameHex string `json:"encrypted_frame_hex"`
		PayloadLen        int    `json:"payload_len"`
	} `json:"s2c_framing_vectors"`
	SequenceRolloverVectors []struct {
		Seq            int    `json:"seq"`
		UnencryptedHex string `json:"unencrypted_hex"`
		EncryptedHex   string `json:"encrypted_hex"`
	} `json:"sequence_rollover_vectors"`
}

func loadGoldenVectors(t *testing.T) GoldenVectors {
	data, err := os.ReadFile("../../../.re_harness/production/RS-UH-PROD-V2/golden_protocol_vectors.json")
	if err != nil {
		t.Fatalf("Failed to read golden_protocol_vectors.json: %v", err)
	}
	var gv GoldenVectors
	if err := json.Unmarshal(data, &gv); err != nil {
		t.Fatalf("Failed to unmarshal golden_protocol_vectors.json: %v", err)
	}
	return gv
}

func parseHexUint32(s string) uint32 {
	var val uint32
	if len(s) > 2 && s[:2] == "0x" {
		s = s[2:]
	}
	b, _ := hex.DecodeString(s)
	for _, byteVal := range b {
		val = (val << 8) | uint32(byteVal)
	}
	return val
}

func parseHexByte(s string) byte {
	if len(s) > 2 && s[:2] == "0x" {
		s = s[2:]
	}
	b, _ := hex.DecodeString(s)
	if len(b) > 0 {
		return b[0]
	}
	return 0
}

func TestKeyDerivationGoldenVectors(t *testing.T) {
	gv := loadGoldenVectors(t)
	for _, vec := range gv.KeyDerivationVectors {
		seed := parseHexUint32(vec.SeedHex)
		expectedKey := byte(vec.DerivedKeyDec)
		actualKey := GerarChaveSecreta(seed)
		if actualKey != expectedKey {
			t.Errorf("GerarChaveSecreta(%s) = 0x%02X; want 0x%02X (%s)", vec.SeedHex, actualKey, expectedKey, vec.DerivedKeyHex)
		}
	}
}

func TestC2SChainedXORReversibility(t *testing.T) {
	gv := loadGoldenVectors(t)
	for _, vec := range gv.C2SFramingVectors {
		key := parseHexByte(vec.KeyHex)
		unenc, _ := hex.DecodeString(vec.UnencryptedHex)
		encExpected, _ := hex.DecodeString(vec.EncryptedHex)

		encActual := CifrarC2S(unenc, key)
		if hex.EncodeToString(encActual) != vec.EncryptedHex {
			t.Errorf("CifrarC2S mismatch: got %x, want %x", encActual, encExpected)
		}

		decActual := DecifrarC2S(encActual, key)
		if hex.EncodeToString(decActual) != vec.UnencryptedHex {
			t.Errorf("DecifrarC2S mismatch: got %x, want %x", decActual, unenc)
		}
	}
}

func TestS2CIndependentXOR(t *testing.T) {
	gv := loadGoldenVectors(t)
	for _, vec := range gv.S2CFramingVectors {
		key := parseHexByte(vec.KeyHex)
		payload, _ := hex.DecodeString(vec.PayloadHex)
		frameExpected, _ := hex.DecodeString(vec.EncryptedFrameHex)

		encPayload := CifrarS2C(payload, key)
		hdr := [2]byte{byte(vec.PayloadLen >> 8), byte(vec.PayloadLen & 0xFF)}
		encHdr := [2]byte{hdr[0] ^ key, hdr[1] ^ key}

		fullEnc := append(encHdr[:], encPayload...)
		if hex.EncodeToString(fullEnc) != vec.EncryptedFrameHex {
			t.Errorf("S2C Frame mismatch: got %x, want %x", fullEnc, frameExpected)
		}

		decLen := DecifrarS2CHeader(encHdr, key)
		if int(decLen) != vec.PayloadLen {
			t.Errorf("DecifrarS2CHeader mismatch: got %d, want %d", decLen, vec.PayloadLen)
		}

		decPayload := DecifrarS2C(encPayload, key)
		if hex.EncodeToString(decPayload) != vec.PayloadHex {
			t.Errorf("DecifrarS2C mismatch: got %x, want %x", decPayload, payload)
		}
	}
}

func TestSequenceRolloverVectors(t *testing.T) {
	gv := loadGoldenVectors(t)
	key := byte(0xAA)
	for _, vec := range gv.SequenceRolloverVectors {
		unenc, _ := hex.DecodeString(vec.UnencryptedHex)
		encExpected, _ := hex.DecodeString(vec.EncryptedHex)

		encActual := CifrarC2S(unenc, key)
		if hex.EncodeToString(encActual) != vec.EncryptedHex {
			t.Errorf("Rollover seq %d mismatch: got %x, want %x", vec.Seq, encActual, encExpected)
		}
	}
}
