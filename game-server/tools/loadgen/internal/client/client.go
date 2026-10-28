package client

import (
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"net"
	"time"

	"returnsaiyan/gameserver/internal/protocol"
	"returnsaiyan/gameserver/tools/loadgen/internal/metrics"
)

type ClientState int

const (
	StateDisconnected ClientState = iota
	StateConnected
	StateAuthenticated
	StateInWorld
	StateClosed
)

// SimulatedClient represents an individual synthetic game client running the full wire protocol.
type SimulatedClient struct {
	ID        int
	target    string
	username  string
	password  string
	conn      net.Conn
	key       byte
	state     ClientState
	token     string
	roleID    int32
	seq       byte
	collector *metrics.Collector
	timeout   time.Duration
}

func NewSimulatedClient(
	id int,
	target string,
	username string,
	password string,
	collector *metrics.Collector,
	timeout time.Duration,
) *SimulatedClient {
	if timeout <= 0 {
		timeout = 5 * time.Second
	}
	return &SimulatedClient{
		ID:        id,
		target:    target,
		username:  username,
		password:  password,
		collector: collector,
		timeout:   timeout,
		state:     StateDisconnected,
	}
}

// Connect dials the TCP server and performs the 7-byte greeting handshake.
func (c *SimulatedClient) Connect() error {
	localAlias := fmt.Sprintf("127.0.0.%d", 2+(c.ID%10))
	dialer := net.Dialer{
		LocalAddr: &net.TCPAddr{IP: net.ParseIP(localAlias)},
		Timeout:   c.timeout,
	}

	conn, err := dialer.Dial("tcp", c.target)
	if err != nil {
		c.collector.IncConnErrors()
		return fmt.Errorf("dial failed: %w", err)
	}
	c.conn = conn

	// Read 7-byte greeting
	_ = c.conn.SetReadDeadline(time.Now().Add(c.timeout))
	var greeting [7]byte
	if _, err := io.ReadFull(c.conn, greeting[:]); err != nil {
		c.conn.Close()
		c.collector.IncConnErrors()
		return fmt.Errorf("failed reading greeting: %w", err)
	}

	if greeting[0] != 0x00 || greeting[1] != 0x05 || greeting[2] != 0x00 {
		c.conn.Close()
		c.collector.IncConnErrors()
		return fmt.Errorf("invalid greeting header: %x", greeting[:3])
	}

	seed := binary.BigEndian.Uint32(greeting[3:7])
	c.key = protocol.GerarChaveSecreta(seed)
	c.state = StateConnected
	c.collector.IncActiveConns()
	return nil
}

func (c *SimulatedClient) Close() {
	if c.conn != nil {
		c.conn.Close()
		c.conn = nil
		c.state = StateClosed
		c.collector.DecActiveConns()
	}
}

// sendAndReceive sends an encrypted C2S packet and waits for decrypted S2C response.
func (c *SimulatedClient) sendAndReceive(pw *protocol.PacketWriter, expectedOpcode byte) (byte, []byte, error) {
	if c.conn == nil {
		return 0, nil, errors.New("client connection is nil")
	}

	rawFrame, err := pw.FinalizeC2S(c.seq)
	if err != nil {
		return 0, nil, fmt.Errorf("finalize failed: %w", err)
	}
	c.seq++

	wirePacket := append(rawFrame[:2], protocol.CifrarC2S(rawFrame[2:], c.key)...)

	start := time.Now()
	_ = c.conn.SetWriteDeadline(time.Now().Add(c.timeout))
	if _, err := c.conn.Write(wirePacket); err != nil {
		c.collector.RecordAction(pw.Opcode(), time.Since(start), false, "write_error")
		return 0, nil, fmt.Errorf("write error: %w", err)
	}
	c.collector.RecordSend(len(wirePacket))

	_ = c.conn.SetReadDeadline(time.Now().Add(c.timeout))
	var encHdr [2]byte
	if _, err := io.ReadFull(c.conn, encHdr[:]); err != nil {
		c.collector.RecordAction(pw.Opcode(), time.Since(start), false, "read_hdr_error")
		return 0, nil, fmt.Errorf("read header error: %w", err)
	}

	payloadLen := protocol.DecifrarS2CHeader(encHdr, c.key)
	if payloadLen < 1 {
		c.collector.RecordAction(pw.Opcode(), time.Since(start), false, "invalid_length")
		return 0, nil, fmt.Errorf("invalid payload length: %d", payloadLen)
	}

	encPayload := make([]byte, payloadLen)
	if _, err := io.ReadFull(c.conn, encPayload); err != nil {
		c.collector.RecordAction(pw.Opcode(), time.Since(start), false, "read_body_error")
		return 0, nil, fmt.Errorf("read payload error: %w", err)
	}
	c.collector.RecordRecv(2 + len(encPayload))

	decPayload := protocol.DecifrarS2C(encPayload, c.key)
	opcode := decPayload[0]
	body := decPayload[1:]

	duration := time.Since(start)
	success := (opcode == expectedOpcode)
	errType := ""
	if !success {
		errType = fmt.Sprintf("opcode_mismatch(got=0x%02X,want=0x%02X)", opcode, expectedOpcode)
	}
	c.collector.RecordAction(pw.Opcode(), duration, success, errType)

	return opcode, body, nil
}

// Register creates an account via Opcode 0x09.
func (c *SimulatedClient) Register() error {
	pw := protocol.NewPacketWriter(protocol.OpcodeRegisterAccount)
	pw.WriteStr(c.username).WriteStr(c.password)

	op, _, err := c.sendAndReceive(pw, protocol.OpcodeRegisterResult)
	if err != nil {
		return err
	}
	if op != protocol.OpcodeRegisterResult {
		return fmt.Errorf("register failed with opcode 0x%02X", op)
	}
	return nil
}

// Login authenticates with the server.
func (c *SimulatedClient) Login() error {
	pw := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
	pw.WriteStr(c.username).WriteStr(c.password).WriteStr("91184").WriteStr("1.0.17")

	op, body, err := c.sendAndReceive(pw, protocol.OpcodeRoleLoginResponse)
	if err != nil {
		return err
	}
	if op == protocol.OpcodeSystemPrompt {
		// Account does not exist: auto-register and retry login
		if regErr := c.Register(); regErr != nil {
			return fmt.Errorf("login failed (opcode 0x07) and registration failed: %w", regErr)
		}
		pwRetry := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
		pwRetry.WriteStr(c.username).WriteStr(c.password).WriteStr("91184").WriteStr("1.0.17")
		op, body, err = c.sendAndReceive(pwRetry, protocol.OpcodeRoleLoginResponse)
		if err != nil {
			return err
		}
	}
	if op != protocol.OpcodeRoleLoginResponse {
		return fmt.Errorf("login failed with opcode 0x%02X", op)
	}

	pr := protocol.NewPacketReader(body)
	token, err := pr.ReadStr()
	if err != nil {
		return fmt.Errorf("failed reading session token: %w", err)
	}
	c.token = token

	roleCount, err := pr.ReadU8()
	if err != nil {
		return fmt.Errorf("failed reading role count: %w", err)
	}
	if roleCount == 0 {
		return errors.New("no roles available for account")
	}

	roleID, err := pr.ReadI32()
	if err != nil {
		return fmt.Errorf("failed reading first role ID: %w", err)
	}
	c.roleID = roleID
	c.state = StateAuthenticated
	return nil
}

// EnterWorld selects character and enters the game world.
func (c *SimulatedClient) EnterWorld() error {
	if c.state != StateAuthenticated {
		return fmt.Errorf("cannot enter world in state %d", c.state)
	}

	pw := protocol.NewPacketWriter(protocol.OpcodeEnterWorld)
	pw.WriteStr(c.token).WriteI32(c.roleID)

	op, _, err := c.sendAndReceive(pw, protocol.OpcodePlayerStatsSync)
	if err != nil {
		return err
	}
	if op != protocol.OpcodePlayerStatsSync {
		return fmt.Errorf("enter world failed with opcode 0x%02X", op)
	}

	c.state = StateInWorld
	return nil
}

// SendMovement sends movement synchronization packet (Opcode 0x20).
func (c *SimulatedClient) SendMovement(x, y, z, heading float32, nonce string) error {
	pw := protocol.NewPacketWriter(protocol.OpcodeEntityMoveSync)
	pw.WriteF32(x).WriteF32(y).WriteF32(z).WriteF32(heading).WriteStr(nonce)

	op, _, err := c.sendAndReceive(pw, protocol.OpcodeEntityMoveSync)
	if err != nil {
		return err
	}
	if op != protocol.OpcodeEntityMoveSync {
		return fmt.Errorf("movement failed with opcode 0x%02X", op)
	}
	return nil
}

// SendSkillCast casts a skill against target (Opcode 0x25).
func (c *SimulatedClient) SendSkillCast(targetID, skillID int32, nonce string) error {
	pw := protocol.NewPacketWriter(protocol.OpcodeSkillCast)
	pw.WriteI32(targetID).WriteI32(skillID).WriteStr(nonce)

	op, _, err := c.sendAndReceive(pw, protocol.OpcodeSkillCast)
	if err != nil {
		return err
	}
	if op != protocol.OpcodeSkillCast {
		return fmt.Errorf("skill cast failed with opcode 0x%02X", op)
	}

	// Consume subsequent Opcode 0x21 Battle Update packet from stream
	_ = c.conn.SetReadDeadline(time.Now().Add(c.timeout))
	var encHdr [2]byte
	if _, err := io.ReadFull(c.conn, encHdr[:]); err == nil {
		payloadLen := protocol.DecifrarS2CHeader(encHdr, c.key)
		if payloadLen > 0 {
			buf := make([]byte, payloadLen)
			_, _ = io.ReadFull(c.conn, buf)
		}
	}

	return nil
}

// SendHeartbeat sends a ping and verifies pong (Opcode 0x27 / 0x28).
func (c *SimulatedClient) SendHeartbeat() error {
	pw := protocol.NewPacketWriter(protocol.OpcodeHeartbeatPing)
	pw.WriteI64(time.Now().UnixMilli())

	op, _, err := c.sendAndReceive(pw, protocol.OpcodeHeartbeatPong)
	if err != nil {
		return err
	}
	if op != protocol.OpcodeHeartbeatPong {
		return fmt.Errorf("heartbeat failed with opcode 0x%02X", op)
	}
	return nil
}
