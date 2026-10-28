package protocol

import (
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"math"
)

var (
	ErrBufferUnderflow  = errors.New("buffer underflow: not enough data to read field")
	ErrStringOverflow   = errors.New("string length overflows packet buffer")
	ErrLengthUnderflow  = errors.New("packet length underflow: length must be at least 2 bytes")
	ErrLengthOverflow   = errors.New("packet length overflow: length exceeds maximum allowable frame size")
	ErrSequenceMismatch = errors.New("sequence number mismatch")
)

const (
	MaxFrameSize = 65535
	GreetingSize = 7
)

// Packet represents a parsed network message.
type Packet struct {
	Seq    byte
	Opcode byte
	Body   []byte
}

// PacketWriter provides big-endian binary packet serialization.
type PacketWriter struct {
	opcode byte
	body   []byte
}

func NewPacketWriter(opcode byte) *PacketWriter {
	return &PacketWriter{
		opcode: opcode,
		body:   make([]byte, 0, 64),
	}
}

func (pw *PacketWriter) Opcode() byte {
	return pw.opcode
}

func (pw *PacketWriter) WriteU8(val byte) *PacketWriter {
	pw.body = append(pw.body, val)
	return pw
}

func (pw *PacketWriter) WriteI16(val int16) *PacketWriter {
	var buf [2]byte
	binary.BigEndian.PutUint16(buf[:], uint16(val))
	pw.body = append(pw.body, buf[:]...)
	return pw
}

func (pw *PacketWriter) WriteU16(val uint16) *PacketWriter {
	var buf [2]byte
	binary.BigEndian.PutUint16(buf[:], val)
	pw.body = append(pw.body, buf[:]...)
	return pw
}

func (pw *PacketWriter) WriteI32(val int32) *PacketWriter {
	var buf [4]byte
	binary.BigEndian.PutUint32(buf[:], uint32(val))
	pw.body = append(pw.body, buf[:]...)
	return pw
}

func (pw *PacketWriter) WriteF32(val float32) *PacketWriter {
	var buf [4]byte
	binary.BigEndian.PutUint32(buf[:], math.Float32bits(val))
	pw.body = append(pw.body, buf[:]...)
	return pw
}

func (pw *PacketWriter) WriteI64(val int64) *PacketWriter {
	var buf [8]byte
	binary.BigEndian.PutUint64(buf[:], uint64(val))
	pw.body = append(pw.body, buf[:]...)
	return pw
}

func (pw *PacketWriter) WriteStr(val string) *PacketWriter {
	strBytes := []byte(val)
	pw.WriteU16(uint16(len(strBytes)))
	pw.body = append(pw.body, strBytes...)
	return pw
}

// WriteS2CStr serializes a string according to client aos::LeitorPacote::str() expectations:
// S2C strings include the null terminator in wire length (L = len + 1), or L = 0 for empty string.
func (pw *PacketWriter) WriteS2CStr(val string) *PacketWriter {
	if len(val) == 0 {
		pw.WriteU16(0)
		return pw
	}
	pw.WriteU16(uint16(len(val) + 1))
	pw.body = append(pw.body, []byte(val)...)
	pw.body = append(pw.body, 0)
	return pw
}

func (pw *PacketWriter) WriteBinary(data []byte) *PacketWriter {
	pw.body = append(pw.body, data...)
	return pw
}

// FinalizeC2S serializes the packet for Client-to-Server framing:
// [2B Length (total_bytes - 2)][1B Seq][1B Opcode][Body...]
func (pw *PacketWriter) FinalizeC2S(seq byte) ([]byte, error) {
	totalLen := len(pw.body) + 4
	payloadLen := totalLen - 2
	if payloadLen > MaxFrameSize {
		return nil, ErrLengthOverflow
	}
	out := make([]byte, totalLen)
	binary.BigEndian.PutUint16(out[0:2], uint16(payloadLen))
	out[2] = seq
	out[3] = pw.opcode
	copy(out[4:], pw.body)
	return out, nil
}

// FinalizeS2C serializes the packet for Server-to-Client framing:
// [2B Length (body_len + 1)][1B Opcode][Body...]
// Encrypted with independent XOR.
func (pw *PacketWriter) FinalizeS2C(key byte) ([]byte, error) {
	payloadLen := len(pw.body) + 1
	if payloadLen > MaxFrameSize {
		return nil, ErrLengthOverflow
	}
	unencPayload := make([]byte, payloadLen)
	unencPayload[0] = pw.opcode
	copy(unencPayload[1:], pw.body)

	encHdr := [2]byte{
		byte(payloadLen>>8) ^ key,
		byte(payloadLen&0xFF) ^ key,
	}
	encPayload := CifrarS2C(unencPayload, key)

	out := make([]byte, 2+payloadLen)
	copy(out[0:2], encHdr[:])
	copy(out[2:], encPayload)
	return out, nil
}

// PacketReader provides sequential deserialization from a decrypted payload buffer.
type PacketReader struct {
	data   []byte
	offset int
}

func NewPacketReader(data []byte) *PacketReader {
	return &PacketReader{data: data, offset: 0}
}

func (pr *PacketReader) Remaining() int {
	return len(pr.data) - pr.offset
}

func (pr *PacketReader) ReadU8() (byte, error) {
	if pr.offset+1 > len(pr.data) {
		return 0, ErrBufferUnderflow
	}
	val := pr.data[pr.offset]
	pr.offset++
	return val, nil
}

func (pr *PacketReader) ReadI16() (int16, error) {
	if pr.offset+2 > len(pr.data) {
		return 0, ErrBufferUnderflow
	}
	val := int16(binary.BigEndian.Uint16(pr.data[pr.offset : pr.offset+2]))
	pr.offset += 2
	return val, nil
}

func (pr *PacketReader) ReadU16() (uint16, error) {
	if pr.offset+2 > len(pr.data) {
		return 0, ErrBufferUnderflow
	}
	val := binary.BigEndian.Uint16(pr.data[pr.offset : pr.offset+2])
	pr.offset += 2
	return val, nil
}

func (pr *PacketReader) ReadI32() (int32, error) {
	if pr.offset+4 > len(pr.data) {
		return 0, ErrBufferUnderflow
	}
	val := int32(binary.BigEndian.Uint32(pr.data[pr.offset : pr.offset+4]))
	pr.offset += 4
	return val, nil
}

func (pr *PacketReader) ReadF32() (float32, error) {
	if pr.offset+4 > len(pr.data) {
		return 0, ErrBufferUnderflow
	}
	val := math.Float32frombits(binary.BigEndian.Uint32(pr.data[pr.offset : pr.offset+4]))
	pr.offset += 4
	return val, nil
}

func (pr *PacketReader) ReadI64() (int64, error) {
	if pr.offset+8 > len(pr.data) {
		return 0, ErrBufferUnderflow
	}
	val := int64(binary.BigEndian.Uint64(pr.data[pr.offset : pr.offset+8]))
	pr.offset += 8
	return val, nil
}

func (pr *PacketReader) ReadStr() (string, error) {
	sLen, err := pr.ReadU16()
	if err != nil {
		return "", err
	}
	if pr.offset+int(sLen) > len(pr.data) {
		return "", ErrStringOverflow
	}
	sBytes := pr.data[pr.offset : pr.offset+int(sLen)]
	pr.offset += int(sLen)
	if len(sBytes) > 0 && sBytes[len(sBytes)-1] == 0 {
		sBytes = sBytes[:len(sBytes)-1]
	}
	return string(sBytes), nil
}

// ReadS2CStr decodes a string encoded in S2C format (length includes null terminator).
func (pr *PacketReader) ReadS2CStr() (string, error) {
	sLen, err := pr.ReadU16()
	if err != nil {
		return "", err
	}
	if sLen == 0 {
		return "", nil
	}
	if pr.offset+int(sLen) > len(pr.data) {
		return "", ErrStringOverflow
	}
	sBytes := pr.data[pr.offset : pr.offset+int(sLen)]
	pr.offset += int(sLen)
	if len(sBytes) > 0 && sBytes[len(sBytes)-1] == 0 {
		sBytes = sBytes[:len(sBytes)-1]
	}
	return string(sBytes), nil
}

func (pr *PacketReader) ReadBinary(n int) ([]byte, error) {
	if pr.offset+n > len(pr.data) {
		return nil, ErrBufferUnderflow
	}
	b := make([]byte, n)
	copy(b, pr.data[pr.offset:pr.offset+n])
	pr.offset += n
	return b, nil
}

// FramingMode indicates whether the stream uses full-frame or plain-header framing.
type FramingMode int

const (
	FramingModeUnknown FramingMode = iota
	FramingModeFullFrame
	FramingModePlainHeader
)

// C2SStreamDecoder reassembles incoming C2S frames across arbitrary TCP chunks.
type C2SStreamDecoder struct {
	key         byte
	mode        FramingMode
	buf         []byte
	expectedSeq byte
	seqInit     bool
}

func NewC2SStreamDecoder(key byte) *C2SStreamDecoder {
	return &C2SStreamDecoder{
		key:  key,
		mode: FramingModeUnknown,
		buf:  make([]byte, 0, 1024),
	}
}

func isKnownC2SOpcode(op byte, bodyLen int) bool {
	switch op {
	case 0x00: // LoginRequest requires username, password, unionId, version (min 10 bytes)
		return bodyLen >= 10
	case 0x10: // Role selection / enter world request
		return bodyLen >= 0
	case 0x12: // Game connection token handshake
		return bodyLen >= 4
	case 0x25: // Language / client settings packet ("player:lang:...")
		return bodyLen >= 0
	case 0x27, 0x28: // Heartbeat ping/pong has 4-byte timestamp
		return bodyLen == 4
	case 0x50: // Role selection / enter world
		return bodyLen >= 4
	case 0x01, 0x04, 0x05, 0x07, 0x08, 0x09, 0x0A, 0x11, 0x20, 0x21, 0x26, 0x29, 0x2E:
		return bodyLen >= 0
	default:
		return false
	}
}

// Feed consumes a raw chunk of received TCP stream and returns all completed Packets.
func (d *C2SStreamDecoder) Feed(chunk []byte) ([]*Packet, error) {
	d.buf = append(d.buf, chunk...)
	var packets []*Packet

	for {
		// Need at least 2 bytes for the frame length header
		if len(d.buf) < 2 {
			break
		}

		// Calculate both hypotheses:
		// 1. Plaintext 2-byte header (synthetic/loadgen)
		plainPayloadLen := int(binary.BigEndian.Uint16(d.buf[0:2]))

		// 2. Full-frame encrypted header (real Android client)
		// C[0] = P[0], C[1] = P[1] ^ P[0] ^ key => P[0] = C[0], P[1] = C[1] ^ C[0] ^ key
		maskedP0 := d.buf[0]
		maskedP1 := d.buf[1] ^ d.buf[0] ^ d.key
		maskedPayloadLen := (int(maskedP0) << 8) | int(maskedP1)

		isPlainValid := false
		if plainPayloadLen >= 2 && plainPayloadLen <= MaxFrameSize && len(d.buf) >= 2+plainPayloadLen {
			pt := DecifrarC2S(d.buf[2:2+plainPayloadLen], d.key)
			if len(pt) >= 2 && isKnownC2SOpcode(pt[1], len(pt)-2) {
				isPlainValid = true
			}
		}

		isFullValid := false
		if maskedPayloadLen >= 2 && maskedPayloadLen <= MaxFrameSize && len(d.buf) >= 2+maskedPayloadLen {
			pt := DecifrarC2S(d.buf[:2+maskedPayloadLen], d.key)
			if len(pt) >= 4 && isKnownC2SOpcode(pt[3], len(pt)-4) {
				isFullValid = true
			}
		}

		if d.mode == FramingModeUnknown {
			// First packet discovery:
			if isFullValid && len(d.buf) >= 2+maskedPayloadLen {
				pt := DecifrarC2S(d.buf[:2+maskedPayloadLen], d.key)
				if len(pt) >= 4 && pt[2] == 0 && isKnownC2SOpcode(pt[3], len(pt)-4) {
					d.mode = FramingModeFullFrame
				}
			}
			if d.mode == FramingModeUnknown && isPlainValid && len(d.buf) >= 2+plainPayloadLen {
				pt := DecifrarC2S(d.buf[2:2+plainPayloadLen], d.key)
				if len(pt) >= 2 && pt[0] == 0 && isKnownC2SOpcode(pt[1], len(pt)-2) {
					d.mode = FramingModePlainHeader
				}
			}
		}

		var isFullFrameEncrypted bool
		var payloadLen int

		if d.mode == FramingModeFullFrame {
			if !isFullValid {
				if len(d.buf) < 2+maskedPayloadLen {
					break
				}
				return nil, fmt.Errorf("%w: invalid full-frame payload len %d", ErrLengthUnderflow, maskedPayloadLen)
			}
			isFullFrameEncrypted = true
			payloadLen = maskedPayloadLen
		} else if d.mode == FramingModePlainHeader {
			if !isPlainValid {
				if len(d.buf) < 2+plainPayloadLen {
					break
				}
				return nil, fmt.Errorf("%w: invalid plain-header payload len %d", ErrLengthUnderflow, plainPayloadLen)
			}
			isFullFrameEncrypted = false
			payloadLen = plainPayloadLen
		} else {
			// Fallback if mode not yet locked (e.g. non-zero starting sequence in unit tests)
			if isPlainValid && !isFullValid {
				isFullFrameEncrypted = false
				payloadLen = plainPayloadLen
			} else if isFullValid && !isPlainValid {
				isFullFrameEncrypted = true
				payloadLen = maskedPayloadLen
			} else if isPlainValid && isFullValid {
				if d.seqInit {
					ptFull := DecifrarC2S(d.buf[:2+maskedPayloadLen], d.key)
					ptPlain := DecifrarC2S(d.buf[2:2+plainPayloadLen], d.key)
					if ptFull[2] == d.expectedSeq && ptPlain[0] != d.expectedSeq {
						isFullFrameEncrypted = true
						payloadLen = maskedPayloadLen
					} else {
						isFullFrameEncrypted = false
						payloadLen = plainPayloadLen
					}
				} else {
					isFullFrameEncrypted = false
					payloadLen = plainPayloadLen
				}
			} else {
				if plainPayloadLen < 2 {
					return nil, fmt.Errorf("%w: got %d bytes", ErrLengthUnderflow, plainPayloadLen)
				}
				if plainPayloadLen > MaxFrameSize {
					return nil, fmt.Errorf("%w: got %d bytes", ErrLengthOverflow, plainPayloadLen)
				}
				if len(d.buf) < 2+plainPayloadLen {
					break
				}
				payloadLen = plainPayloadLen
			}
		}

		totalFrameLen := 2 + payloadLen
		var seq, opcode byte
		var body []byte

		if isFullFrameEncrypted {
			plaintext := DecifrarC2S(d.buf[:totalFrameLen], d.key)
			seq = plaintext[2]
			opcode = plaintext[3]
			body = plaintext[4:]
		} else {
			ciphertext := d.buf[2:totalFrameLen]
			plaintext := DecifrarC2S(ciphertext, d.key)
			seq = plaintext[0]
			opcode = plaintext[1]
			body = plaintext[2:]
		}

		// Sequence validation (rollover modulo 256)
		if !d.seqInit {
			d.expectedSeq = seq
			d.seqInit = true
		} else {
			expected := (d.expectedSeq + 1) & 0xFF
			if seq != expected {
				d.expectedSeq = seq
			} else {
				d.expectedSeq = expected
			}
		}

		packetBody := make([]byte, len(body))
		copy(packetBody, body)
		packets = append(packets, &Packet{
			Seq:    seq,
			Opcode: opcode,
			Body:   packetBody,
		})

		// Advance buffer
		d.buf = d.buf[totalFrameLen:]
	}

	return packets, nil
}

// BuildServerGreeting constructs the initial 7-byte handshake packet sent to client.
func BuildServerGreeting(seed uint32) []byte {
	out := make([]byte, 7)
	// Default prefix hypothesis: 0x00, 0x05, 0x00
	out[0] = 0x00
	out[1] = 0x05
	out[2] = 0x00
	binary.BigEndian.PutUint32(out[3:7], seed)
	return out
}

// ReadFull reads exactly len(buf) from r.
func ReadFull(r io.Reader, buf []byte) error {
	_, err := io.ReadFull(r, buf)
	return err
}
