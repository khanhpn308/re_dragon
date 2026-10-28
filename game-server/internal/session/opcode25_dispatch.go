package session

import (
	"log/slog"
	"strings"

	"returnsaiyan/gameserver/internal/protocol"
	"returnsaiyan/gameserver/internal/transport/tcp"
)

// classifyOpcode25RPC recognizes a *complete* C2S length-prefixed ASCII
// command. A readable substring within a binary combat packet is not enough:
// this prevents arbitrary skill payloads from being interpreted as UI RPCs.
// This classification does not establish the original client's S2C schema.
func classifyOpcode25RPC(body []byte) (string, bool) {
	if len(body) < 5 || len(body) > 4096 {
		return "", false
	}
	reader := protocol.NewPacketReader(body)
	command, err := reader.ReadStr()
	if err != nil || reader.Remaining() != 0 || len(command) < 3 {
		return "", false
	}
	namespace, action, ok := strings.Cut(command, ":")
	if !ok || namespace == "" || action == "" {
		return "", false
	}
	for i, c := range command {
		if c < 0x21 || c > 0x7e {
			return "", false
		}
		if i < len(namespace) && !((c >= 'a' && c <= 'z') ||
			(c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_') {
			return "", false
		}
	}
	return command, true
}

// handleOpcode25 separates the observed colon-delimited client RPC transport
// from the existing binary combat implementation without remapping opcodes.
func (h *AuthHandler) handleOpcode25(conn *tcp.ClientConn, pkt *protocol.Packet) error {
	if command, ok := classifyOpcode25RPC(pkt.Body); ok {
		return h.handleClientRPC(conn, command)
	}
	return h.handleSkillCast(conn, pkt)
}

func (h *AuthHandler) handleClientRPC(conn *tcp.ClientConn, command string) error {
	if strings.HasPrefix(command, "player:lang:") {
		h.logger.Info("client language setting received", slog.String("lang", command))
		return nil
	}
	if strings.HasPrefix(command, "drawCard:") {
		// The authenticated client S2C contract (including mType initialization,
		// actual wish-x1 request, cost and result layout) is NOT verified.
		// Sending an invented response would risk corrupting client state.
		h.logger.Error("P3b BLOCKED: drawCard RPC lacks verified client S2C contract",
			slog.String("cmd", command),
			slog.String("conn_id", conn.ID()))
		return nil
	}
	h.logger.Info("client command RPC received", slog.String("cmd", command))
	return nil
}
