package session

import (
	"encoding/binary"
	"io"
	"log/slog"
	"net"
	"os"
	"testing"
	"time"

	"returnsaiyan/gameserver/internal/domain/world"
	"returnsaiyan/gameserver/internal/protocol"
	"returnsaiyan/gameserver/internal/transport/tcp"
)

type mockNotifier struct {
	conns map[string]*tcp.ClientConn
}

func (m *mockNotifier) GetConn(connID string) (*tcp.ClientConn, bool) {
	c, ok := m.conns[connID]
	return c, ok
}

func setupTestServer(t *testing.T) (net.Listener, *LocalAuthenticator, *SessionManager, *AuthHandler, *mockNotifier) {
	t.Helper()
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to bind loopback test listener: %v", err)
	}

	auth := NewLocalAuthenticator()
	sm := NewSessionManager(10 * time.Minute)
	notifier := &mockNotifier{conns: make(map[string]*tcp.ClientConn)}
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
	handler := NewAuthHandler(auth, sm, notifier, "127.0.0.1", 30001, logger)
	we := world.NewWorldEngine(50 * time.Millisecond)
	handler.SetWorldEngine(we)

	return l, auth, sm, handler, notifier
}

// performHandshakeClient connects to the test server, reads the 7-byte greeting, and returns the session XOR key.
func performHandshakeClient(t *testing.T, rawConn net.Conn) byte {
	t.Helper()
	var greeting [7]byte
	if _, err := io.ReadFull(rawConn, greeting[:]); err != nil {
		t.Fatalf("failed to read handshake greeting: %v", err)
	}

	if greeting[0] != 0x00 || greeting[1] != 0x05 || greeting[2] != 0x00 {
		t.Fatalf("invalid greeting header: %x", greeting[:3])
	}

	seed := binary.BigEndian.Uint32(greeting[3:7])
	return protocol.GerarChaveSecreta(seed)
}

// sendC2SPacket encrypts and sends a C2S packet. Length header (2 bytes) is plaintext; payload is encrypted with C2S chained XOR.
func sendC2SPacket(t *testing.T, rawConn net.Conn, pw *protocol.PacketWriter, seq byte, key byte) {
	t.Helper()
	rawFrame, err := pw.FinalizeC2S(seq)
	if err != nil {
		t.Fatalf("failed to finalize C2S packet: %v", err)
	}
	encPayload := protocol.CifrarC2S(rawFrame[2:], key)
	wirePacket := append(rawFrame[:2], encPayload...)
	if _, err := rawConn.Write(wirePacket); err != nil {
		t.Fatalf("failed to write C2S packet: %v", err)
	}
}

// readS2CPacket reads and decrypts an S2C packet.
func readS2CPacket(t *testing.T, rawConn net.Conn, key byte) (byte, []byte) {
	t.Helper()
	var encHdr [2]byte
	if _, err := io.ReadFull(rawConn, encHdr[:]); err != nil {
		t.Fatalf("failed to read S2C length header: %v", err)
	}
	payloadLen := protocol.DecifrarS2CHeader(encHdr, key)
	if payloadLen < 1 {
		t.Fatalf("invalid S2C payload length: %d", payloadLen)
	}

	encPayload := make([]byte, payloadLen)
	if _, err := io.ReadFull(rawConn, encPayload); err != nil {
		t.Fatalf("failed to read S2C payload (%d bytes): %v", payloadLen, err)
	}

	decPayload := protocol.DecifrarS2C(encPayload, key)
	opcode := decPayload[0]
	body := decPayload[1:]
	return opcode, body
}

func TestHandler_LoginSuccess(t *testing.T) {
	listener, _, _, handler, _ := setupTestServer(t)
	defer listener.Close()

	// Accept in background
	go func() {
		rawConn, err := listener.Accept()
		if err != nil {
			return
		}
		logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
		c, err := tcp.NewClientConn("conn_test_login", rawConn, handler, 2*time.Second, 2*time.Second, logger)
		if err != nil {
			return
		}
		_ = c.Start()
	}()

	client, err := net.Dial("tcp", listener.Addr().String())
	if err != nil {
		t.Fatalf("failed to dial: %v", err)
	}
	defer client.Close()

	key := performHandshakeClient(t, client)

	// Send LoginRequest (Opcode 0x00)
	pw := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
	pw.WriteStr("testuser").WriteStr("password123").WriteStr("91184").WriteStr("aos-arm64/1.0.17")
	sendC2SPacket(t, client, pw, 0, key)

	// Receive RoleLoginResponse (Opcode 0x01)
	opcode, body := readS2CPacket(t, client, key)
	if opcode != protocol.OpcodeRoleLoginResponse {
		t.Fatalf("expected opcode 0x01, got 0x%02X", opcode)
	}

	pr := protocol.NewPacketReader(body)
	token, err := pr.ReadStr()
	if err != nil || len(token) != 64 {
		t.Fatalf("expected 64-char hex token, got %q (err: %v)", token, err)
	}

	serverCount, err := pr.ReadU8()
	if err != nil || serverCount != 1 {
		t.Fatalf("expected 1 server, got %d (err: %v)", serverCount, err)
	}

	r1ID, _ := pr.ReadI32()
	r1Name, _ := pr.ReadStr()
	r1IP, _ := pr.ReadStr()
	if r1ID != 1 || r1Name != "ReturnSaiyan Unified" || r1IP != "127.0.0.1" {
		t.Fatalf("unexpected server 1: id=%d, name=%s, ip=%s", r1ID, r1Name, r1IP)
	}
}

func TestHandler_LoginBadPassword(t *testing.T) {
	listener, _, _, handler, _ := setupTestServer(t)
	defer listener.Close()

	go func() {
		rawConn, err := listener.Accept()
		if err != nil {
			return
		}
		logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
		c, _ := tcp.NewClientConn("conn_test_bad_pass", rawConn, handler, 2*time.Second, 2*time.Second, logger)
		_ = c.Start()
	}()

	client, err := net.Dial("tcp", listener.Addr().String())
	if err != nil {
		t.Fatalf("failed to dial: %v", err)
	}
	defer client.Close()

	key := performHandshakeClient(t, client)

	// Send LoginRequest with incorrect password
	pw := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
	pw.WriteStr("testuser").WriteStr("incorrectpass").WriteStr("91184").WriteStr("aos-arm64/1.0.17")
	sendC2SPacket(t, client, pw, 0, key)

	// Receive SystemPrompt (Opcode 0x07)
	opcode, body := readS2CPacket(t, client, key)
	if opcode != protocol.OpcodeSystemPrompt {
		t.Fatalf("expected opcode 0x07 (SystemPrompt), got 0x%02X", opcode)
	}

	pr := protocol.NewPacketReader(body)
	msg, err := pr.ReadStr()
	if err != nil || msg != "Invalid username or password." {
		t.Fatalf("unexpected error message: %q", msg)
	}
}

func TestHandler_HeartbeatPingPong(t *testing.T) {
	listener, _, _, handler, _ := setupTestServer(t)
	defer listener.Close()

	go func() {
		rawConn, err := listener.Accept()
		if err != nil {
			return
		}
		logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
		c, _ := tcp.NewClientConn("conn_test_ping", rawConn, handler, 2*time.Second, 2*time.Second, logger)
		_ = c.Start()
	}()

	client, err := net.Dial("tcp", listener.Addr().String())
	if err != nil {
		t.Fatalf("failed to dial: %v", err)
	}
	defer client.Close()

	key := performHandshakeClient(t, client)

	// Send Heartbeat Ping (Opcode 0x27) with timestamp 123456789
	pw := protocol.NewPacketWriter(protocol.OpcodeHeartbeatPing)
	pw.WriteI32(123456789)
	sendC2SPacket(t, client, pw, 0, key)

	// Expect Heartbeat Pong (Opcode 0x28) with same timestamp
	opcode, body := readS2CPacket(t, client, key)
	if opcode != protocol.OpcodeHeartbeatPong {
		t.Fatalf("expected opcode 0x28 (Pong), got 0x%02X", opcode)
	}

	pr := protocol.NewPacketReader(body)
	echoTS, err := pr.ReadI32()
	if err != nil || echoTS != 123456789 {
		t.Fatalf("expected echoed timestamp 123456789, got %d", echoTS)
	}
}

func TestHandler_EnterWorldRoleAuthorization(t *testing.T) {
	listener, _, _, handler, _ := setupTestServer(t)
	defer listener.Close()

	go func() {
		rawConn, err := listener.Accept()
		if err != nil {
			return
		}
		logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
		c, _ := tcp.NewClientConn("conn_test_world", rawConn, handler, 2*time.Second, 2*time.Second, logger)
		_ = c.Start()
	}()

	client, err := net.Dial("tcp", listener.Addr().String())
	if err != nil {
		t.Fatalf("failed to dial: %v", err)
	}
	defer client.Close()

	key := performHandshakeClient(t, client)

	// 1. Log in as testuser (owns roles 101, 102)
	pwLogin := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
	pwLogin.WriteStr("testuser").WriteStr("password123").WriteStr("91184").WriteStr("1.0.17")
	sendC2SPacket(t, client, pwLogin, 0, key)

	_, bodyLogin := readS2CPacket(t, client, key)
	prLogin := protocol.NewPacketReader(bodyLogin)
	token, _ := prLogin.ReadStr()

	// 2. Try to enter world with unauthorized role ID 201 (UltraEgoDev, owned by developer!)
	pwBadRole := protocol.NewPacketWriter(protocol.OpcodeEnterWorld)
	pwBadRole.WriteStr(token).WriteI32(201)
	sendC2SPacket(t, client, pwBadRole, 1, key)

	opcodeBad, bodyBad := readS2CPacket(t, client, key)
	if opcodeBad != protocol.OpcodeSystemPrompt {
		t.Fatalf("expected SystemPrompt for unauthorized role, got 0x%02X", opcodeBad)
	}
	prBad := protocol.NewPacketReader(bodyBad)
	badMsg, _ := prBad.ReadStr()
	if badMsg != "Unauthorized: Selected character does not belong to your account." {
		t.Fatalf("unexpected rejection message: %s", badMsg)
	}

	// 3. Enter world with authorized role ID 101 (SaiyanGoku)
	pwGoodRole := protocol.NewPacketWriter(protocol.OpcodeEnterWorld)
	pwGoodRole.WriteStr(token).WriteI32(101)
	sendC2SPacket(t, client, pwGoodRole, 2, key)

	opcodeGood, bodyGood := readS2CPacket(t, client, key)
	if opcodeGood != protocol.OpcodePlayerStatsSync {
		t.Fatalf("expected PlayerStatsSync (0x10), got 0x%02X", opcodeGood)
	}
	prGood := protocol.NewPacketReader(bodyGood)
	rID, _ := prGood.ReadI32()
	_, _ = prGood.ReadI64()
	rLevel, _ := prGood.ReadI32()
	_, _ = prGood.ReadI32()
	_, _ = prGood.ReadI32()
	_, _ = prGood.ReadI32()
	_, _ = prGood.ReadI32()
	_, _ = prGood.ReadI32()
	_, _ = prGood.ReadU8()
	rName, _ := prGood.ReadStr()
	if rID != 101 || rLevel != 50 || rName != "SaiyanGoku" {
		t.Fatalf("unexpected character sync data: id=%d level=%d name=%s", rID, rLevel, rName)
	}
}

func TestHandler_DuplicateLoginEviction(t *testing.T) {
	listener, _, _, handler, notifier := setupTestServer(t)
	defer listener.Close()

	// Server accept loop
	go func() {
		connCount := 0
		for {
			rawConn, err := listener.Accept()
			if err != nil {
				return
			}
			connCount++
			connID := "conn_socket_" + string(rune('0'+connCount))
			logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
			c, err := tcp.NewClientConn(connID, rawConn, handler, 2*time.Second, 2*time.Second, logger)
			if err != nil {
				return
			}
			notifier.conns[connID] = c
			_ = c.Start()
		}
	}()

	// 1. Client 1 logs in
	c1, err := net.Dial("tcp", listener.Addr().String())
	if err != nil {
		t.Fatalf("failed to dial c1: %v", err)
	}
	defer c1.Close()
	k1 := performHandshakeClient(t, c1)

	pw1 := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
	pw1.WriteStr("testuser").WriteStr("password123").WriteStr("91184").WriteStr("1.0.17")
	sendC2SPacket(t, c1, pw1, 0, k1)

	op1, _ := readS2CPacket(t, c1, k1)
	if op1 != protocol.OpcodeRoleLoginResponse {
		t.Fatalf("expected c1 login response 0x01, got 0x%02X", op1)
	}

	// 2. Client 2 logs in with same credentials
	c2, err := net.Dial("tcp", listener.Addr().String())
	if err != nil {
		t.Fatalf("failed to dial c2: %v", err)
	}
	defer c2.Close()
	k2 := performHandshakeClient(t, c2)

	pw2 := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
	pw2.WriteStr("testuser").WriteStr("password123").WriteStr("91184").WriteStr("1.0.17")
	sendC2SPacket(t, c2, pw2, 0, k2)

	op2, _ := readS2CPacket(t, c2, k2)
	if op2 != protocol.OpcodeRoleLoginResponse {
		t.Fatalf("expected c2 login response 0x01, got 0x%02X", op2)
	}

	// 3. Client 1 must receive Opcode 0x07 with eviction notice
	_ = c1.SetReadDeadline(time.Now().Add(1 * time.Second))
	opEvict, bodyEvict := readS2CPacket(t, c1, k1)
	if opEvict != protocol.OpcodeSystemPrompt {
		t.Fatalf("expected eviction notification 0x07 on client 1, got 0x%02X", opEvict)
	}
	prEvict := protocol.NewPacketReader(bodyEvict)
	evictMsg, _ := prEvict.ReadStr()
	if evictMsg != "Your account has logged in from another device." {
		t.Fatalf("unexpected eviction message: %q", evictMsg)
	}
}

func TestHandler_EntityMovementAndSkillCast(t *testing.T) {
	listener, _, _, handler, notifier := setupTestServer(t)
	defer listener.Close()

	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			c, _ := tcp.NewClientConn("conn_test_world_actions", conn, handler, 5*time.Second, 5*time.Second, slog.Default())
			notifier.conns[c.ID()] = c
			_ = c.Start()
		}
	}()

	client, err := net.Dial("tcp", listener.Addr().String())
	if err != nil {
		t.Fatalf("failed to dial: %v", err)
	}
	defer client.Close()

	key := performHandshakeClient(t, client)

	// 1. Login
	pwLogin := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
	pwLogin.WriteStr("testuser").WriteStr("password123").WriteStr("91184").WriteStr("1.0.17")
	sendC2SPacket(t, client, pwLogin, 0, key)

	opLogin, bodyLogin := readS2CPacket(t, client, key)
	if opLogin != protocol.OpcodeRoleLoginResponse {
		t.Fatalf("expected opcode 0x01, got 0x%02X", opLogin)
	}
	prLogin := protocol.NewPacketReader(bodyLogin)
	token, _ := prLogin.ReadStr()

	// 2. Enter World with Role 101 (SaiyanGoku)
	pwEnter := protocol.NewPacketWriter(protocol.OpcodeEnterWorld)
	pwEnter.WriteStr(token).WriteI32(101)
	sendC2SPacket(t, client, pwEnter, 1, key)

	opEnter, _ := readS2CPacket(t, client, key)
	if opEnter != protocol.OpcodePlayerStatsSync {
		t.Fatalf("expected opcode 0x10 player sync, got 0x%02X", opEnter)
	}

	// 3. Movement Sync (Opcode 0x20): Move to (120, 120, 0, 45)
	pwMove := protocol.NewPacketWriter(protocol.OpcodeEntityMoveSync)
	pwMove.WriteF32(120).WriteF32(120).WriteF32(0).WriteF32(45).WriteStr("move_nonce_1")
	sendC2SPacket(t, client, pwMove, 2, key)

	opMove, bodyMove := readS2CPacket(t, client, key)
	if opMove != protocol.OpcodeEntityMoveSync {
		t.Fatalf("expected opcode 0x20 movement confirmation, got 0x%02X", opMove)
	}
	prMove := protocol.NewPacketReader(bodyMove)
	roleID, _ := prMove.ReadI32()
	x, _ := prMove.ReadF32()
	y, _ := prMove.ReadF32()
	if roleID != 101 || x != 120 || y != 120 {
		t.Fatalf("unexpected move confirmation: role=%d x=%.1f y=%.1f", roleID, x, y)
	}

	// 4. Skill Cast (Opcode 0x25): Cast Kamehameha (101) on Saibaman Alpha (1001)
	pwCast := protocol.NewPacketWriter(protocol.OpcodeSkillCast)
	pwCast.WriteI32(1001).WriteI32(101).WriteStr("skill_nonce_1")
	sendC2SPacket(t, client, pwCast, 3, key)

	// Expect Opcode 0x25 confirmation
	opCast, bodyCast := readS2CPacket(t, client, key)
	if opCast != protocol.OpcodeSkillCast {
		t.Fatalf("expected opcode 0x25 skill cast confirmation, got 0x%02X", opCast)
	}
	prCast := protocol.NewPacketReader(bodyCast)
	casterID, _ := prCast.ReadI32()
	targetID, _ := prCast.ReadI32()
	skillID, _ := prCast.ReadI32()
	damage, _ := prCast.ReadI32()
	targetHP, _ := prCast.ReadI32()
	if casterID != 101 || targetID != 1001 || skillID != 101 || damage <= 0 || targetHP < 0 {
		t.Fatalf("unexpected skill cast: caster=%d target=%d skill=%d dmg=%d hp=%d", casterID, targetID, skillID, damage, targetHP)
	}

	// Expect Opcode 0x21 Battle Update
	opBattle, _ := readS2CPacket(t, client, key)
	if opBattle != protocol.OpcodeBattleUpdate {
		t.Fatalf("expected opcode 0x21 battle update, got 0x%02X", opBattle)
	}

	// 5. Chat Message (Opcode 0x29)
	pwChat := protocol.NewPacketWriter(protocol.OpcodeChatMessage)
	pwChat.WriteU8(1).WriteStr("Kamehameha fired!")
	sendC2SPacket(t, client, pwChat, 4, key)

	opChat, bodyChat := readS2CPacket(t, client, key)
	if opChat != protocol.OpcodeChatMessage {
		t.Fatalf("expected opcode 0x29 chat echo, got 0x%02X", opChat)
	}
	prChat := protocol.NewPacketReader(bodyChat)
	ch, _ := prChat.ReadU8()
	sender, _ := prChat.ReadStr()
	msg, _ := prChat.ReadStr()
	if ch != 1 || sender != "SaiyanGoku" || msg != "Kamehameha fired!" {
		t.Fatalf("unexpected chat message: ch=%d sender=%q msg=%q", ch, sender, msg)
	}
}
