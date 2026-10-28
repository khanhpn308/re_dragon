package protocol

import (
	"bytes"
	"testing"
)

func TestPacketWriterReaderRoundtrip(t *testing.T) {
	pw := NewPacketWriter(0x10)
	pw.WriteU8(42)
	pw.WriteI16(-1234)
	pw.WriteU16(5678)
	pw.WriteI32(-999999)
	pw.WriteI64(12345678901234)
	pw.WriteStr("ReturnSaiyan")
	pw.WriteBinary([]byte{0xDE, 0xAD, 0xBE, 0xEF})

	frame, err := pw.FinalizeC2S(7)
	if err != nil {
		t.Fatalf("FinalizeC2S failed: %v", err)
	}

	// Payload starts at offset 4 (after 2B len, 1B seq, 1B opcode)
	body := frame[4:]
	pr := NewPacketReader(body)

	u8, err := pr.ReadU8()
	if err != nil || u8 != 42 {
		t.Errorf("ReadU8 = %d, err = %v; want 42", u8, err)
	}
	i16, err := pr.ReadI16()
	if err != nil || i16 != -1234 {
		t.Errorf("ReadI16 = %d, err = %v; want -1234", i16, err)
	}
	u16, err := pr.ReadU16()
	if err != nil || u16 != 5678 {
		t.Errorf("ReadU16 = %d, err = %v; want 5678", u16, err)
	}
	i32, err := pr.ReadI32()
	if err != nil || i32 != -999999 {
		t.Errorf("ReadI32 = %d, err = %v; want -999999", i32, err)
	}
	i64, err := pr.ReadI64()
	if err != nil || i64 != 12345678901234 {
		t.Errorf("ReadI64 = %d, err = %v; want 12345678901234", i64, err)
	}
	s, err := pr.ReadStr()
	if err != nil || s != "ReturnSaiyan" {
		t.Errorf("ReadStr = %s, err = %v; want 'ReturnSaiyan'", s, err)
	}
	bin, err := pr.ReadBinary(4)
	if err != nil || !bytes.Equal(bin, []byte{0xDE, 0xAD, 0xBE, 0xEF}) {
		t.Errorf("ReadBinary = %x, err = %v; want DEADBEEF", bin, err)
	}
	if pr.Remaining() != 0 {
		t.Errorf("Remaining = %d; want 0", pr.Remaining())
	}
}

func TestStreamDecoderFragmentation(t *testing.T) {
	seed := uint32(0x12345678)
	key := GerarChaveSecreta(seed)

	pw := NewPacketWriter(0x27)
	pw.WriteI32(100)
	rawFrame, err := pw.FinalizeC2S(0)
	if err != nil {
		t.Fatalf("FinalizeC2S failed: %v", err)
	}

	// Encrypt the payload part
	encPayload := CifrarC2S(rawFrame[2:], key)
	wirePacket := append(rawFrame[:2], encPayload...)

	decoder := NewC2SStreamDecoder(key)

	// Feed byte-by-byte (extreme fragmentation)
	var completePackets []*Packet
	for i := 0; i < len(wirePacket); i++ {
		pkts, err := decoder.Feed(wirePacket[i : i+1])
		if err != nil {
			t.Fatalf("Feed error at byte %d: %v", i, err)
		}
		completePackets = append(completePackets, pkts...)
	}

	if len(completePackets) != 1 {
		t.Fatalf("Expected 1 packet, got %d", len(completePackets))
	}
	pkt := completePackets[0]
	if pkt.Opcode != 0x27 || pkt.Seq != 0 {
		t.Errorf("Packet mismatch: Opcode=0x%02X, Seq=%d", pkt.Opcode, pkt.Seq)
	}
}

func TestStreamDecoderCoalescing(t *testing.T) {
	seed := uint32(0xDEADBEEF)
	key := GerarChaveSecreta(seed)

	var streamBuffer []byte
	const numPackets = 10

	for seq := 0; seq < numPackets; seq++ {
		pw := NewPacketWriter(0x27)
		pw.WriteI32(int32(seq * 100))
		rawFrame, err := pw.FinalizeC2S(byte(seq))
		if err != nil {
			t.Fatalf("FinalizeC2S failed: %v", err)
		}
		encPayload := CifrarC2S(rawFrame[2:], key)
		wirePacket := append(rawFrame[:2], encPayload...)
		streamBuffer = append(streamBuffer, wirePacket...)
	}

	decoder := NewC2SStreamDecoder(key)
	// Feed all packets in a single chunk
	pkts, err := decoder.Feed(streamBuffer)
	if err != nil {
		t.Fatalf("Feed coalesced failed: %v", err)
	}

	if len(pkts) != numPackets {
		t.Fatalf("Expected %d packets, got %d", numPackets, len(pkts))
	}

	for i, pkt := range pkts {
		if pkt.Seq != byte(i) {
			t.Errorf("Packet %d seq = %d; want %d", i, pkt.Seq, i)
		}
		if pkt.Opcode != 0x27 {
			t.Errorf("Packet %d opcode = 0x%02X; want 0x27", i, pkt.Opcode)
		}
		pr := NewPacketReader(pkt.Body)
		val, err := pr.ReadI32()
		if err != nil || val != int32(i*100) {
			t.Errorf("Packet %d body val = %d, err = %v; want %d", i, val, err, i*100)
		}
	}
}

func TestStreamDecoderSequenceRollover(t *testing.T) {
	key := byte(0x33)
	decoder := NewC2SStreamDecoder(key)

	// Send sequence 254 -> 255 -> 0 -> 1
	seqs := []byte{254, 255, 0, 1}
	for _, s := range seqs {
		pw := NewPacketWriter(0x27).WriteI32(1)
		rawFrame, _ := pw.FinalizeC2S(s)
		encPayload := CifrarC2S(rawFrame[2:], key)
		wire := append(rawFrame[:2], encPayload...)

		pkts, err := decoder.Feed(wire)
		if err != nil {
			t.Fatalf("Feed failed for seq %d: %v", s, err)
		}
		if len(pkts) != 1 || pkts[0].Seq != s {
			t.Fatalf("Expected packet seq %d, got %+v", s, pkts)
		}
	}
}

func TestStreamDecoderLengthValidation(t *testing.T) {
	key := byte(0x11)
	decoder := NewC2SStreamDecoder(key)

	// Length underflow: payload length = 1
	badFrame := []byte{0x00, 0x01, 0xFF}
	_, err := decoder.Feed(badFrame)
	if err == nil {
		t.Error("Expected error for length underflow, got nil")
	}
}

func FuzzStreamDecoder(f *testing.F) {
	// Seed with valid and invalid byte sequences
	f.Add([]byte{0x00, 0x05, 0x11, 0x22, 0x33, 0x44, 0x55})
	f.Add([]byte{0x00, 0x01, 0xFF})
	f.Add([]byte{0xFF, 0xFF, 0x00, 0x00})
	f.Add([]byte{})

	f.Fuzz(func(t *testing.T, data []byte) {
		decoder := NewC2SStreamDecoder(0x42)
		// Decoder should never panic on arbitrary input bytes
		_, _ = decoder.Feed(data)
	})
}

func TestRealAndroidLoginPacket(t *testing.T) {
	// Golden wire hex captured from physical RMX3461 device
	wireHex := []byte{
		0x00, 0x40, 0x3b, 0x41, 0x3a, 0x44, 0x06, 0x4c, 0x06, 0x45, 0x0a, 0x71, 0x1a, 0x00, 0x14, 0x1c,
		0x4a, 0x50, 0x59, 0x4f, 0x02, 0x4d, 0x19, 0x53, 0x06, 0x4d, 0x18, 0x52, 0x1e, 0x0b, 0x1e, 0x64,
		0x1f, 0x6b, 0x77, 0x79, 0x67, 0x6f, 0x60, 0x29, 0x62, 0x2b, 0x61, 0x22, 0x6f, 0x25, 0x6a, 0x26,
		0x6e, 0x15, 0x64, 0x6d, 0x78, 0x67, 0x25, 0x6c, 0x7f, 0x6e, 0x2c, 0x3f, 0x3c,
	}

	key := byte(0x7B)
	decoder := NewC2SStreamDecoder(key)
	packets, err := decoder.Feed(wireHex)
	if err != nil {
		t.Fatalf("Feed error: %v", err)
	}
	if len(packets) != 1 {
		t.Fatalf("expected 1 packet, got %d", len(packets))
	}
	pkt := packets[0]
	if pkt.Opcode != OpcodeRoleLoginResponse { // 0x01
		t.Errorf("expected Opcode 0x01, got 0x%02X", pkt.Opcode)
	}
	if pkt.Seq != 0 {
		t.Errorf("expected Seq 0, got %d", pkt.Seq)
	}

	pr := NewPacketReader(pkt.Body)
	unionID, err := pr.ReadStr()
	if err != nil {
		t.Fatalf("read unionID err: %v", err)
	}
	if unionID != "91184" {
		t.Errorf("expected unionID '91184', got '%s'", unionID)
	}
	version, err := pr.ReadStr()
	if err != nil {
		t.Fatalf("read version err: %v", err)
	}
	if version != "aos-arm64/1.0.17" {
		t.Errorf("expected version 'aos-arm64/1.0.17', got '%s'", version)
	}
}
