package tcp

import (
	"encoding/binary"
	"io"
	"log/slog"
	"net"
	"sync"
	"testing"
	"time"

	"returnsaiyan/gameserver/internal/protocol"
)

// echoHandler echoes PING (0x27) with PONG (0x28) containing the same timestamp.
type echoHandler struct {
	receivedPackets []*protocol.Packet
	mtx             sync.Mutex
}

func (h *echoHandler) HandlePacket(conn *ClientConn, pkt *protocol.Packet) error {
	h.mtx.Lock()
	h.receivedPackets = append(h.receivedPackets, pkt)
	h.mtx.Unlock()

	if pkt.Opcode == 0x27 { // HEARTBEAT_PING
		pr := protocol.NewPacketReader(pkt.Body)
		ts, err := pr.ReadI32()
		if err != nil {
			return err
		}
		// Send PONG (0x28)
		pw := protocol.NewPacketWriter(0x28).WriteI32(ts)
		return conn.SendPacket(pw)
	}
	return nil
}

// clientSession emulates an actual game client socket.
type clientSession struct {
	conn net.Conn
	seed uint32
	key  byte
	seq  byte
}

func connectClient(t *testing.T, addr string) *clientSession {
	conn, err := net.Dial("tcp", addr)
	if err != nil {
		t.Fatalf("Failed to dial TCP server: %v", err)
	}

	// Read initial 7-byte greeting
	greeting := make([]byte, 7)
	if _, err := io.ReadFull(conn, greeting); err != nil {
		t.Fatalf("Failed to read greeting: %v", err)
	}

	seed := binary.BigEndian.Uint32(greeting[3:7])
	key := protocol.GerarChaveSecreta(seed)

	return &clientSession{
		conn: conn,
		seed: seed,
		key:  key,
		seq:  0,
	}
}

func (cs *clientSession) sendPacket(t *testing.T, opcode byte, bodyWriter func(pw *protocol.PacketWriter)) {
	pw := protocol.NewPacketWriter(opcode)
	if bodyWriter != nil {
		bodyWriter(pw)
	}

	rawFrame, err := pw.FinalizeC2S(cs.seq)
	if err != nil {
		t.Fatalf("FinalizeC2S failed: %v", err)
	}
	cs.seq = (cs.seq + 1) & 0xFF

	encPayload := protocol.CifrarC2S(rawFrame[2:], cs.key)
	wirePacket := append(rawFrame[:2], encPayload...)

	if _, err := cs.conn.Write(wirePacket); err != nil {
		t.Fatalf("Client write failed: %v", err)
	}
}

func (cs *clientSession) readS2CPacket(t *testing.T) (byte, []byte) {
	// Read 2-byte encrypted header
	var encHdr [2]byte
	if _, err := io.ReadFull(cs.conn, encHdr[:]); err != nil {
		t.Fatalf("Failed to read S2C header: %v", err)
	}

	payloadLen := protocol.DecifrarS2CHeader(encHdr, cs.key)
	if payloadLen < 1 {
		t.Fatalf("Invalid S2C payload length: %d", payloadLen)
	}

	encPayload := make([]byte, payloadLen)
	if _, err := io.ReadFull(cs.conn, encPayload); err != nil {
		t.Fatalf("Failed to read S2C payload: %v", err)
	}

	decPayload := protocol.DecifrarS2C(encPayload, cs.key)
	opcode := decPayload[0]
	body := decPayload[1:]

	return opcode, body
}

func (cs *clientSession) close() {
	_ = cs.conn.Close()
}

func TestServerHandshakeAndPingPong(t *testing.T) {
	handler := &echoHandler{}
	cfg := Config{
		Addr:           "127.0.0.1:0", // Ephemeral loopback port
		ReadTimeout:    5 * time.Second,
		WriteTimeout:   5 * time.Second,
		MaxConnections: 10,
	}
	srv := NewServer(cfg, handler, slog.Default())
	if err := srv.Start(); err != nil {
		t.Fatalf("Server start failed: %v", err)
	}
	defer srv.Stop(2 * time.Second)

	client := connectClient(t, srv.Addr().String())
	defer client.close()

	// Send PING with timestamp 987654321
	client.sendPacket(t, 0x27, func(pw *protocol.PacketWriter) {
		pw.WriteI32(987654321)
	})

	// Receive PONG
	op, body := client.readS2CPacket(t)
	if op != 0x28 {
		t.Fatalf("Expected PONG opcode 0x28, got 0x%02X", op)
	}
	pr := protocol.NewPacketReader(body)
	ts, err := pr.ReadI32()
	if err != nil || ts != 987654321 {
		t.Fatalf("PONG timestamp mismatch: got %d, want 987654321", ts)
	}
}

func TestServerFragmentedDelivery(t *testing.T) {
	handler := &echoHandler{}
	cfg := Config{
		Addr:           "127.0.0.1:0",
		ReadTimeout:    5 * time.Second,
		WriteTimeout:   5 * time.Second,
		MaxConnections: 10,
	}
	srv := NewServer(cfg, handler, slog.Default())
	if err := srv.Start(); err != nil {
		t.Fatalf("Server start failed: %v", err)
	}
	defer srv.Stop(2 * time.Second)

	client := connectClient(t, srv.Addr().String())
	defer client.close()

	// Prepare PING frame
	pw := protocol.NewPacketWriter(0x27).WriteI32(55555)
	rawFrame, _ := pw.FinalizeC2S(0)
	encPayload := protocol.CifrarC2S(rawFrame[2:], client.key)
	wire := append(rawFrame[:2], encPayload...)

	// Send 1 byte at a time over TCP link with small delays
	for i := 0; i < len(wire); i++ {
		if _, err := client.conn.Write(wire[i : i+1]); err != nil {
			t.Fatalf("Fragmented write failed at %d: %v", i, err)
		}
		time.Sleep(1 * time.Millisecond)
	}

	// Server should reassemble and respond
	op, body := client.readS2CPacket(t)
	if op != 0x28 {
		t.Fatalf("Expected opcode 0x28, got 0x%02X", op)
	}
	pr := protocol.NewPacketReader(body)
	ts, _ := pr.ReadI32()
	if ts != 55555 {
		t.Fatalf("PONG timestamp mismatch: got %d, want 55555", ts)
	}
}

func TestServerCoalescedPackets(t *testing.T) {
	handler := &echoHandler{}
	cfg := Config{
		Addr:           "127.0.0.1:0",
		ReadTimeout:    5 * time.Second,
		WriteTimeout:   5 * time.Second,
		MaxConnections: 10,
	}
	srv := NewServer(cfg, handler, slog.Default())
	if err := srv.Start(); err != nil {
		t.Fatalf("Server start failed: %v", err)
	}
	defer srv.Stop(2 * time.Second)

	client := connectClient(t, srv.Addr().String())
	defer client.close()

	// Prepare 5 coalesced PING frames
	var coalesced []byte
	const count = 5
	for i := 0; i < count; i++ {
		pw := protocol.NewPacketWriter(0x27).WriteI32(int32(i + 1))
		rawFrame, _ := pw.FinalizeC2S(byte(i))
		encPayload := protocol.CifrarC2S(rawFrame[2:], client.key)
		wire := append(rawFrame[:2], encPayload...)
		coalesced = append(coalesced, wire...)
	}

	// Write all in one TCP segment
	if _, err := client.conn.Write(coalesced); err != nil {
		t.Fatalf("Coalesced write failed: %v", err)
	}

	// Read 5 corresponding PONG responses
	for i := 0; i < count; i++ {
		op, body := client.readS2CPacket(t)
		if op != 0x28 {
			t.Fatalf("Response %d expected opcode 0x28, got 0x%02X", i, op)
		}
		pr := protocol.NewPacketReader(body)
		ts, _ := pr.ReadI32()
		if ts != int32(i+1) {
			t.Fatalf("Response %d expected timestamp %d, got %d", i, i+1, ts)
		}
	}
}

func TestServerNegativeMalformedPacket(t *testing.T) {
	handler := &echoHandler{}
	cfg := Config{
		Addr:           "127.0.0.1:0",
		ReadTimeout:    2 * time.Second,
		WriteTimeout:   2 * time.Second,
		MaxConnections: 10,
	}
	srv := NewServer(cfg, handler, slog.Default())
	if err := srv.Start(); err != nil {
		t.Fatalf("Server start failed: %v", err)
	}
	defer srv.Stop(2 * time.Second)

	client := connectClient(t, srv.Addr().String())
	defer client.close()

	// Send an illegal frame length: payload length 0
	badFrame := []byte{0x00, 0x00}
	if _, err := client.conn.Write(badFrame); err != nil {
		t.Fatalf("Write bad frame failed: %v", err)
	}

	// Connection should be closed by server due to length underflow
	buf := make([]byte, 16)
	_ = client.conn.SetReadDeadline(time.Now().Add(1 * time.Second))
	_, err := client.conn.Read(buf)
	if err == nil {
		t.Error("Expected server to disconnect on malformed frame, but read succeeded")
	}
}

func TestServerGracefulShutdown(t *testing.T) {
	handler := &echoHandler{}
	cfg := Config{
		Addr:           "127.0.0.1:0",
		ReadTimeout:    5 * time.Second,
		WriteTimeout:   5 * time.Second,
		MaxConnections: 10,
	}
	srv := NewServer(cfg, handler, slog.Default())
	if err := srv.Start(); err != nil {
		t.Fatalf("Server start failed: %v", err)
	}

	client := connectClient(t, srv.Addr().String())
	defer client.close()

	if srv.ActiveConnections() != 1 {
		t.Fatalf("Expected 1 active connection, got %d", srv.ActiveConnections())
	}

	// Stop server with 2 second timeout
	if err := srv.Stop(2 * time.Second); err != nil {
		t.Fatalf("Stop failed: %v", err)
	}

	if srv.ActiveConnections() != 0 {
		t.Fatalf("Expected 0 active connections after stop, got %d", srv.ActiveConnections())
	}
}
