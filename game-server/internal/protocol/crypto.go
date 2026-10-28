package protocol

// GerarChaveSecreta generates the 1-byte session XOR key from the 32-bit handshake seed.
// Exact machine-code replica of aos::gerarChaveSecreta at 0x007ec838 in libaos_jogo.so.
func GerarChaveSecreta(seed uint32) byte {
	// eor w8, w0, w0, lsl #11
	w8 := seed ^ (seed << 11)
	// eor w8, w8, w8, asr #8 (Arithmetic signed shift)
	shifted := uint32(int32(w8) >> 8)
	w8 = w8 ^ shifted
	// eor w0, w8, 0x045edf26
	w0 := w8 ^ 0x045edf26
	return byte(w0 & 0xFF)
}

// CifrarC2S encrypts client-to-server bytes using the chained XOR cipher.
// Replica of aos::cifrarC2S at 0x007ec850 in libaos_jogo.so.
//
//	C[0] = P[0]
//	C[i] = C[i-1] ^ key ^ P[i]
func CifrarC2S(plaintext []byte, key byte) []byte {
	if len(plaintext) == 0 {
		return nil
	}
	ciphertext := make([]byte, len(plaintext))
	prev := key
	for i, pt := range plaintext {
		ct := prev ^ key ^ pt
		ciphertext[i] = ct
		prev = ct
	}
	return ciphertext
}

// DecifrarC2S decrypts client-to-server bytes using the chained XOR cipher.
// Replica of aos::decifrarC2S at 0x007ec874 in libaos_jogo.so.
//
//	P[0] = C[0]
//	P[i] = C[i-1] ^ key ^ C[i]
func DecifrarC2S(ciphertext []byte, key byte) []byte {
	if len(ciphertext) == 0 {
		return nil
	}
	plaintext := make([]byte, len(ciphertext))
	prev := key
	for i, ct := range ciphertext {
		pt := prev ^ key ^ ct
		plaintext[i] = pt
		prev = ct
	}
	return plaintext
}

// CifrarS2C encrypts server-to-client payload using independent byte-wise XOR.
func CifrarS2C(data []byte, key byte) []byte {
	out := make([]byte, len(data))
	for i, b := range data {
		out[i] = b ^ key
	}
	return out
}

// DecifrarS2C decrypts server-to-client payload using independent byte-wise XOR.
func DecifrarS2C(data []byte, key byte) []byte {
	return CifrarS2C(data, key)
}

// DecifrarS2CHeader decrypts the 2-byte server-to-client frame length header.
func DecifrarS2CHeader(header [2]byte, key byte) uint16 {
	b0 := header[0] ^ key
	b1 := header[1] ^ key
	return (uint16(b0) << 8) | uint16(b1)
}
