package session

import (
	"fmt"
	"log/slog"
	"strconv"
	"sync"
	"time"

	"returnsaiyan/gameserver/internal/domain/world"
	"returnsaiyan/gameserver/internal/protocol"
	"returnsaiyan/gameserver/internal/transport/tcp"
)

// EvictionNotifier allows notifying an active TCP connection when its session is evicted.
type EvictionNotifier interface {
	GetConn(connID string) (*tcp.ClientConn, bool)
}

// AuthHandler handles authentication and session protocol requests.
type AuthHandler struct {
	auth       Authenticator
	sessions   *SessionManager
	notifier   EvictionNotifier
	world      *world.WorldEngine
	logger     *slog.Logger
	serverHost string
	serverPort int32
	mu         sync.Mutex
}

// SetWorldEngine configures the server-authoritative world loop engine.
func (h *AuthHandler) SetWorldEngine(we *world.WorldEngine) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.world = we
}

func (h *AuthHandler) GetWorldEngine() *world.WorldEngine {
	h.mu.Lock()
	defer h.mu.Unlock()
	return h.world
}

// NewAuthHandler creates a new AuthHandler.
func NewAuthHandler(
	auth Authenticator,
	sessions *SessionManager,
	notifier EvictionNotifier,
	serverHost string,
	serverPort int32,
	logger *slog.Logger,
) *AuthHandler {
	if serverHost == "" {
		serverHost = "127.0.0.1"
	}
	if serverPort <= 0 {
		serverPort = 30001
	}
	return &AuthHandler{
		auth:       auth,
		sessions:   sessions,
		notifier:   notifier,
		serverHost: serverHost,
		serverPort: serverPort,
		logger:     logger.With(slog.String("module", "session_handler")),
	}
}

// HandlePacket processes incoming client packets.
func (h *AuthHandler) HandlePacket(conn *tcp.ClientConn, pkt *protocol.Packet) error {
	switch pkt.Opcode {
	case protocol.OpcodeLoginRequest, protocol.OpcodeRoleLoginResponse:
		return h.handleLogin(conn, pkt)
	case protocol.OpcodeHeartbeatPing:
		return h.handleHeartbeat(conn, pkt)
	case protocol.OpcodeEnterWorld, protocol.OpcodePlayerStatsSync:
		return h.handleEnterWorld(conn, pkt)
	case protocol.OpcodeEntitySpawn:
		return h.handleGameHandshake(conn, pkt)
	case protocol.OpcodeRegisterAccount:
		return h.handleRegister(conn, pkt)
	case protocol.OpcodeEntityMoveSync:
		return h.handleMovement(conn, pkt)
	case protocol.OpcodeSkillCast:
		return h.handleOpcode25(conn, pkt)
	case protocol.OpcodeChatMessage:
		return h.handleChatMessage(conn, pkt)
	default:
		h.logger.Debug("unhandled opcode in auth handler",
			slog.String("conn_id", conn.ID()),
			slog.String("opcode", fmt.Sprintf("0x%02X", pkt.Opcode)),
		)
		return nil
	}
}

func isNumeric(s string) bool {
	if len(s) == 0 {
		return false
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}

// handleLogin processes account login request (Opcode 0x00 or Opcode 0x01).
func (h *AuthHandler) handleLogin(conn *tcp.ClientConn, pkt *protocol.Packet) error {
	pr := protocol.NewPacketReader(pkt.Body)
	str1, err := pr.ReadStr()
	if err != nil {
		return fmt.Errorf("failed to read login header string: %w", err)
	}

	var username, password, unionID, version string

	// Detect if this is real Android client (str1 is numeric unionId e.g. "91184")
	if isNumeric(str1) && pr.Remaining() > 10 {
		unionID = str1
		version, _ = pr.ReadStr()
		// Next 3 bytes are channel / platform flags (e.g. b"nn\x01")
		if pr.Remaining() >= 3 {
			_, _ = pr.ReadBinary(3)
		}
		username, _ = pr.ReadStr()
		password, _ = pr.ReadStr()
	} else {
		// Standard / loadgen format: username, password, unionId, version
		username = str1
		password, _ = pr.ReadStr()
		unionID, _ = pr.ReadStr()
		version, _ = pr.ReadStr()
	}

	// SEC-GAME-001: Redact credentials in logs
	h.logger.Info("login request received",
		slog.String("conn_id", conn.ID()),
		slog.String("username", username),
		slog.String("union_id", unionID),
		slog.String("version", version),
	)

	ctx := conn.Context()
	acc, err := h.auth.Authenticate(ctx, username, password)
	if err != nil {
		// Auto-register new guest/test accounts
		if regAcc, regErr := h.auth.Register(ctx, username, password); regErr == nil {
			acc = regAcc
			h.logger.Info("auto-registered new account", slog.String("username", username))
		} else {
			h.logger.Warn("authentication failed",
				slog.String("conn_id", conn.ID()),
				slog.String("username", username),
				slog.String("reason", err.Error()),
			)

			// Send Opcode 0x07 (System Prompt) with error message
			pw := protocol.NewPacketWriter(protocol.OpcodeSystemPrompt)
			pw.WriteS2CStr("Invalid username or password.")
			return conn.SendPacket(pw)
		}
	}

	// Fetch roles owned by the account
	roles, err := h.auth.GetRoles(ctx, acc.ID)
	if err != nil {
		h.logger.Error("failed to retrieve account roles", slog.String("error", err.Error()))
		roles = make([]*Role, 0)
	}

	// Auto-provision a starter role if account has none
	if len(roles) == 0 {
		suffix := username
		if len(suffix) > 4 {
			suffix = suffix[len(suffix)-4:]
		}
		starterRole := &Role{
			Name:     fmt.Sprintf("Saiyan_%s", suffix),
			HeroCode: "10001",
			Level:    1,
			Gender:   1,
			Status:   0,
			Vip:      1,
			Guild:    "Universe 7",
			Online:   0,
		}
		if addErr := h.auth.AddRole(ctx, acc.ID, starterRole); addErr == nil {
			roles = append(roles, starterRole)
			h.logger.Info("auto-provisioned starter character",
				slog.String("username", username),
				slog.Int("role_id", int(starterRole.ID)),
				slog.String("role_name", starterRole.Name),
			)
		} else {
			h.logger.Warn("failed to auto-provision starter role", slog.String("error", addErr.Error()))
		}
	}

	// Create or replace session with duplicate login eviction
	newSess, evictedSess, err := h.sessions.CreateSession(acc, roles, conn.ID())
	if err != nil {
		return fmt.Errorf("failed to create session: %w", err)
	}

	if evictedSess != nil {
		h.logger.Info("evicting previous active session",
			slog.String("username", username),
			slog.String("old_conn_id", evictedSess.ConnID()),
			slog.String("new_conn_id", conn.ID()),
		)
		// If the previous session is still connected, notify and disconnect it
		if h.notifier != nil && evictedSess.ConnID() != "" {
			if oldConn, ok := h.notifier.GetConn(evictedSess.ConnID()); ok {
				pwEvict := protocol.NewPacketWriter(protocol.OpcodeSystemPrompt)
				pwEvict.WriteS2CStr("Your account has logged in from another device.")
				_ = oldConn.SendPacket(pwEvict)
				// Close old connection after brief grace window so eviction packet flushes to socket
				go func(c *tcp.ClientConn) {
					time.Sleep(25 * time.Millisecond)
					_ = c.Close()
				}(oldConn)
			}
		}
	}

	// Build Opcode 0x01 (Role/Server Login Response) matching AArch64 $_6 at 0x007f0a0c
	pw := protocol.NewPacketWriter(protocol.OpcodeRoleLoginResponse)
	pw.WriteS2CStr(newSess.Token())
	pw.WriteU8(1) // 1 server entry

	// Server Entry 1:
	pw.WriteI32(1)                         // server_id
	pw.WriteS2CStr("ReturnSaiyan Unified") // server_name
	pw.WriteS2CStr(h.serverHost)           // server_ip ("127.0.0.1")
	pw.WriteI16(int16(h.serverPort))       // server_port (30001)
	pw.WriteU8(1)                          // status (1 = Smooth)
	pw.WriteU8(1)                          // zoneId (1)
	pw.WriteU8(1)                          // rolec (1)
	pw.WriteS2CStr("Universe 7")           // serDscr ("Universe 7")
	pw.WriteU8(1)                          // newSev (1 = true)
	pw.WriteU8(1)                          // recommond (1 = true, default/lastLoginSev)
	pw.WriteI32(int32(time.Now().Unix()))  // loginCount

	// Server host string and role JSON count (i16) + role JSON array for client roleList
	pw.WriteS2CStr(fmt.Sprintf("%s:%d", h.serverHost, h.serverPort))
	pw.WriteI16(int16(len(roles)))
	for _, r := range roles {
		roleJSON := fmt.Sprintf(`{"serverId":1,"uuid":"%d","name":"%s","lv":%d,"vipLv":%d,"head":7518,"headFrame":1}`,
			r.ID, r.Name, r.Level, r.Vip)
		pw.WriteS2CStr(roleJSON)
	}

	h.logger.Info("login successful, session established",
		slog.String("username", username),
		slog.String("conn_id", conn.ID()),
		slog.Int("role_count", len(roles)),
	)

	return conn.SendPacket(pw)
}

// handleHeartbeat processes Opcode 0x27: heartbeat ping and emits Opcode 0x28.
func (h *AuthHandler) handleHeartbeat(conn *tcp.ClientConn, pkt *protocol.Packet) error {
	pr := protocol.NewPacketReader(pkt.Body)
	ts, err := pr.ReadI32()
	if err != nil {
		return fmt.Errorf("failed to read ping timestamp: %w", err)
	}

	// Touch active session if bound to this connection
	if sess, err := h.sessions.GetSessionByConn(conn.ID()); err == nil {
		_ = h.sessions.TouchSession(sess.Token())
	}

	// Echo back Opcode 0x28 (Pong)
	pw := protocol.NewPacketWriter(protocol.OpcodeHeartbeatPong)
	pw.WriteI32(ts)
	return conn.SendPacket(pw)
}

// handleGameHandshake processes Opcode 0x12: game server connection token handshake.
func (h *AuthHandler) handleGameHandshake(conn *tcp.ClientConn, pkt *protocol.Packet) error {
	pr := protocol.NewPacketReader(pkt.Body)
	token, err := pr.ReadStr()
	if err != nil {
		return fmt.Errorf("failed to read handshake token: %w", err)
	}

	h.logger.Info("game server handshake token received",
		slog.String("conn_id", conn.ID()),
		slog.String("token", token),
	)

	sess, err := h.sessions.GetSession(token)
	if err != nil {
		h.logger.Warn("game server handshake failed: session not found",
			slog.String("conn_id", conn.ID()),
			slog.String("token", token),
		)
		pw := protocol.NewPacketWriter(protocol.OpcodeSystemPrompt)
		pw.WriteS2CStr("Invalid session token. Please log in again.")
		return conn.SendPacket(pw)
	}

	// Rebind this game connection to the active session
	if _, bindErr := h.sessions.BindConn(token, conn.ID()); bindErr != nil {
		h.logger.Warn("failed to bind conn to session", slog.String("error", bindErr.Error()))
	}

	roles := sess.Roles()
	h.logger.Info("game server handshake successful",
		slog.String("conn_id", conn.ID()),
		slog.String("username", sess.Account().Username),
		slog.Int("roles", len(roles)),
	)

	// Send S2C Opcode 0x12: role count + role string IDs matching AArch64 $_12 at 0x7f57b0
	pw := protocol.NewPacketWriter(protocol.OpcodeEntitySpawn)
	pw.WriteU8(byte(len(roles)))
	for _, r := range roles {
		pw.WriteS2CStr(fmt.Sprintf("%d", r.ID))
	}
	return conn.SendPacket(pw)
}

// handleEnterWorld processes Opcode 0x10 / Opcode 0x50: role selection and game world entry.
func (h *AuthHandler) handleEnterWorld(conn *tcp.ClientConn, pkt *protocol.Packet) error {
	pr := protocol.NewPacketReader(pkt.Body)
	var token string
	var roleID int32

	if pr.Remaining() >= 2 {
		if s, err := pr.ReadStr(); err == nil {
			if len(s) == 64 && !isNumeric(s) {
				token = s
				if pr.Remaining() >= 4 {
					roleID, _ = pr.ReadI32()
				}
			} else if isNumeric(s) {
				if id, convErr := strconv.Atoi(s); convErr == nil {
					roleID = int32(id)
				}
			}
		} else {
			pr2 := protocol.NewPacketReader(pkt.Body)
			roleID, _ = pr2.ReadI32()
		}
	}

	var sess *Session
	if token != "" {
		sess, _ = h.sessions.GetSession(token)
	}
	if sess == nil {
		sess, _ = h.sessions.GetSessionByConn(conn.ID())
	}
	if sess == nil {
		h.logger.Warn("enter world rejected: session not found", slog.String("conn_id", conn.ID()))
		pw := protocol.NewPacketWriter(protocol.OpcodeSystemPrompt)
		pw.WriteS2CStr("Session expired or invalid. Please log in again.")
		return conn.SendPacket(pw)
	}

	// If roleID is 0 or unassigned, select the first available role in session
	roles := sess.Roles()
	if roleID == 0 && len(roles) > 0 {
		roleID = roles[0].ID
	}

	selectedRole, err := sess.SelectRole(roleID)
	if err != nil {
		h.logger.Warn("enter world rejected: unauthorized role selection",
			slog.String("conn_id", conn.ID()),
			slog.Int("role_id", int(roleID)),
			slog.String("reason", err.Error()),
		)
		pw := protocol.NewPacketWriter(protocol.OpcodeSystemPrompt)
		pw.WriteS2CStr("Unauthorized: Selected character does not belong to your account.")
		return conn.SendPacket(pw)
	}

	if err := sess.TransitionTo(StateInWorld); err != nil {
		h.logger.Warn("enter world state transition error", slog.String("error", err.Error()))
	}

	h.mu.Lock()
	we := h.world
	h.mu.Unlock()
	if we != nil {
		if z, err := we.GetZone(1); err == nil {
			p := world.NewPlayerEntity(
				selectedRole.ID,
				sess.Account().Username,
				selectedRole.Name,
				selectedRole.HeroCode,
				selectedRole.Level,
				conn.ID(),
				world.Position{X: 100, Y: 100, Z: 0, Heading: 0},
			)
			_ = z.AddPlayer(p)
		}
	}

	h.logger.Info("player entered world",
		slog.String("username", sess.Account().Username),
		slog.Int("role_id", int(selectedRole.ID)),
		slog.String("role_name", selectedRole.Name),
		slog.String("hero_code", selectedRole.HeroCode),
	)

	// Emit initial player sync confirmation (Opcode 0x10) matching AArch64 $_13 at 0x7f5a8c
	pwSync := protocol.NewPacketWriter(protocol.OpcodePlayerStatsSync)
	pwSync.WriteI32(selectedRole.ID)           // [x19] roleID
	pwSync.WriteI64(0)                         // [x19, #8] exp
	pwSync.WriteI32(int32(selectedRole.Level)) // [x19, #16] level
	pwSync.WriteI32(1000)                      // [x19, #24] gold
	pwSync.WriteI32(500)                       // [x19, #28] diamond
	pwSync.WriteI32(int32(selectedRole.Vip))   // [x19, #32] vip
	pwSync.WriteI32(10000)                     // [x19, #36] battle power
	pwSync.WriteI32(0)                         // GuanKa stage count (0 = skip)
	pwSync.WriteU8(byte(selectedRole.Gender))  // [x19, #40] gender
	pwSync.WriteS2CStr(selectedRole.Name)      // [x19, #56] name
	pwSync.WriteI32(1000)                      // [x19, #20] hp
	pwSync.WriteI32(100)                       // [x19, #44] mp
	pwSync.WriteU8(0)                          // flag
	pwSync.WriteI32(100)                       // stamina
	pwSync.WriteU8(0)                          // flag (offset 160: 0 -> NextState(7))
	pwSync.WriteI32(100)                       // [x19, #80] attr1
	pwSync.WriteI32(100)                       // [x19, #84] attr2
	pwSync.WriteI32(100)                       // [x19, #124] attr3
	pwSync.WriteI32(100)                       // [x19, #92] attr4
	pwSync.WriteI32(0)                         // config
	pwSync.WriteI32(100)                       // attr5
	pwSync.WriteI32(100)                       // [x19, #88] attr6
	pwSync.WriteI32(100)                       // [x19, #152] attr7
	pwSync.WriteI32(100)                       // [x19, #156] attr8
	pwSync.WriteU8(0)                          // team member count (0 = skip)
	pwSync.WriteI32(0)                         // team count (0 = skip)
	pwSync.WriteI16(0)                         // extra1
	pwSync.WriteI32(0)                         // [x19, #48] extra2
	pwSync.WriteI64(0)                         // [x19, #104] extra3
	pwSync.WriteU8(0)                          // [x19, #112] extra4
	pwSync.WriteI32(0)                         // [x19, #116] extra5
	pwSync.WriteI32(0)                         // [x19, #120] extra6
	pwSync.WriteI32(0)                         // [x19, #96] extra7
	pwSync.WriteU8(0)                          // [x20, #72] extra8
	pwSync.WriteU8(0)                          // [x20, #76] friends count (0 = skip)
	pwSync.WriteI32(0)                         // collection count (0 = skip)
	return conn.SendPacket(pwSync)
}

// handleRegister processes Opcode 0x09: account registration request.
func (h *AuthHandler) handleRegister(conn *tcp.ClientConn, pkt *protocol.Packet) error {
	pr := protocol.NewPacketReader(pkt.Body)
	username, err := pr.ReadStr()
	if err != nil {
		return fmt.Errorf("failed to read register username: %w", err)
	}
	password, err := pr.ReadStr()
	if err != nil {
		return fmt.Errorf("failed to read register password: %w", err)
	}

	ctx := conn.Context()
	acc, err := h.auth.Register(ctx, username, password)
	if err != nil {
		h.logger.Warn("account registration failed",
			slog.String("username", username),
			slog.String("reason", err.Error()),
		)
		pw := protocol.NewPacketWriter(protocol.OpcodeSystemPrompt)
		pw.WriteS2CStr(fmt.Sprintf("Registration failed: %s", err.Error()))
		return conn.SendPacket(pw)
	}

	h.logger.Info("account registered successfully",
		slog.String("username", acc.Username),
		slog.Int64("account_id", acc.ID),
	)

	pw := protocol.NewPacketWriter(protocol.OpcodeRegisterResult)
	pw.WriteU8(1) // Success flag
	pw.WriteS2CStr("Account created successfully. You may now log in.")
	return conn.SendPacket(pw)
}

// handleMovement processes Opcode 0x20: spatial movement synchronization.
func (h *AuthHandler) handleMovement(conn *tcp.ClientConn, pkt *protocol.Packet) error {
	pr := protocol.NewPacketReader(pkt.Body)
	x, err := pr.ReadF32()
	if err != nil {
		return fmt.Errorf("failed to read move X: %w", err)
	}
	y, err := pr.ReadF32()
	if err != nil {
		return fmt.Errorf("failed to read move Y: %w", err)
	}
	z, err := pr.ReadF32()
	if err != nil {
		return fmt.Errorf("failed to read move Z: %w", err)
	}
	heading, err := pr.ReadF32()
	if err != nil {
		return fmt.Errorf("failed to read move heading: %w", err)
	}
	nonce, _ := pr.ReadStr()

	sess, err := h.sessions.GetSessionByConn(conn.ID())
	if err != nil || sess.State() != StateInWorld || sess.SelectedRole() == nil {
		pw := protocol.NewPacketWriter(protocol.OpcodeSystemPrompt)
		pw.WriteS2CStr("Cannot move: character is not in world.")
		return conn.SendPacket(pw)
	}

	role := sess.SelectedRole()
	h.mu.Lock()
	we := h.world
	h.mu.Unlock()

	if we == nil {
		// Standalone echo mode if world engine is unconfigured
		pw := protocol.NewPacketWriter(protocol.OpcodeEntityMoveSync)
		pw.WriteI32(role.ID)
		pw.WriteF32(x).WriteF32(y).WriteF32(z).WriteF32(heading)
		return conn.SendPacket(pw)
	}

	target := world.Position{X: x, Y: y, Z: z, Heading: heading}
	confirmedPos, err := we.ProcessMovement(1, role.ID, target, nonce, time.Now().UTC())
	if err != nil {
		h.logger.Warn("movement rejected",
			slog.String("conn_id", conn.ID()),
			slog.Int("role_id", int(role.ID)),
			slog.String("reason", err.Error()),
		)
		// Snap player back to authoritative position
		pwSnap := protocol.NewPacketWriter(protocol.OpcodeEntityMoveSync)
		pwSnap.WriteI32(role.ID)
		pwSnap.WriteF32(confirmedPos.X).WriteF32(confirmedPos.Y).WriteF32(confirmedPos.Z).WriteF32(confirmedPos.Heading)
		return conn.SendPacket(pwSnap)
	}

	pw := protocol.NewPacketWriter(protocol.OpcodeEntityMoveSync)
	pw.WriteI32(role.ID)
	pw.WriteF32(confirmedPos.X).WriteF32(confirmedPos.Y).WriteF32(confirmedPos.Z).WriteF32(confirmedPos.Heading)
	return conn.SendPacket(pw)
}

// handleSkillCast processes the binary combat form of Opcode 0x25.
func (h *AuthHandler) handleSkillCast(conn *tcp.ClientConn, pkt *protocol.Packet) error {
	pr := protocol.NewPacketReader(pkt.Body)
	targetID, err := pr.ReadI32()
	if err != nil {
		return fmt.Errorf("failed to read target ID: %w", err)
	}
	skillID, err := pr.ReadI32()
	if err != nil {
		return fmt.Errorf("failed to read skill ID: %w", err)
	}
	nonce, _ := pr.ReadStr()

	sess, err := h.sessions.GetSessionByConn(conn.ID())
	if err != nil || sess.State() != StateInWorld || sess.SelectedRole() == nil {
		pw := protocol.NewPacketWriter(protocol.OpcodeSystemPrompt)
		pw.WriteS2CStr("Cannot cast skill: character is not in world.")
		return conn.SendPacket(pw)
	}

	role := sess.SelectedRole()
	h.mu.Lock()
	we := h.world
	h.mu.Unlock()

	if we == nil {
		pw := protocol.NewPacketWriter(protocol.OpcodeActionConfirm)
		pw.WriteI32(1)
		pw.WriteS2CStr("World engine offline")
		return conn.SendPacket(pw)
	}

	event, err := we.ProcessSkillCast(1, role.ID, targetID, skillID, nonce, time.Now().UTC())
	if err != nil {
		h.logger.Warn("skill execution rejected",
			slog.String("conn_id", conn.ID()),
			slog.Int("role_id", int(role.ID)),
			slog.Int("skill_id", int(skillID)),
			slog.String("reason", err.Error()),
		)
		pwConfirm := protocol.NewPacketWriter(protocol.OpcodeActionConfirm)
		pwConfirm.WriteI32(1) // Error code
		pwConfirm.WriteS2CStr(err.Error())
		return conn.SendPacket(pwConfirm)
	}

	// 1. Emit Opcode 0x25 confirmation
	pwCast := protocol.NewPacketWriter(protocol.OpcodeSkillCast)
	pwCast.WriteI32(event.CasterID)
	pwCast.WriteI32(event.TargetID)
	pwCast.WriteI32(event.SkillID)
	pwCast.WriteI32(event.DamageDealt)
	pwCast.WriteI32(event.TargetRemainingHP)
	var died byte = 0
	if event.TargetDied {
		died = 1
	}
	pwCast.WriteU8(died)
	if err := conn.SendPacket(pwCast); err != nil {
		return err
	}

	// 2. Emit Opcode 0x21 battle update
	pwBattle := protocol.NewPacketWriter(protocol.OpcodeBattleUpdate)
	pwBattle.WriteI32(event.TargetID)
	pwBattle.WriteI32(event.TargetRemainingHP)
	pwBattle.WriteI32(event.CasterRemainingMP)
	return conn.SendPacket(pwBattle)
}

// handleChatMessage processes Opcode 0x29: chat channel broadcasting.
func (h *AuthHandler) handleChatMessage(conn *tcp.ClientConn, pkt *protocol.Packet) error {
	pr := protocol.NewPacketReader(pkt.Body)
	channel, err := pr.ReadU8()
	if err != nil {
		return fmt.Errorf("failed to read chat channel: %w", err)
	}
	msg, err := pr.ReadStr()
	if err != nil {
		return fmt.Errorf("failed to read chat message: %w", err)
	}

	sess, err := h.sessions.GetSessionByConn(conn.ID())
	senderName := "System"
	if err == nil && sess.SelectedRole() != nil {
		senderName = sess.SelectedRole().Name
	}

	pw := protocol.NewPacketWriter(protocol.OpcodeChatMessage)
	pw.WriteU8(channel)
	pw.WriteS2CStr(senderName)
	pw.WriteS2CStr(msg)
	return conn.SendPacket(pw)
}
