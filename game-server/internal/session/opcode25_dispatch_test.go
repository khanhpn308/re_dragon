package session

import (
	"encoding/binary"
	"testing"
)

func opcode25CommandForTest(command string) []byte {
	buf := make([]byte, 2+len(command))
	binary.BigEndian.PutUint16(buf, uint16(len(command)))
	copy(buf[2:], command)
	return buf
}

func TestOpcode25RPCAndSkillPacketClassification(t *testing.T) {
	for _, command := range []string{
		"drawCard:open:1",
		"drawCard:wish:1",
		"player:lang:vi",
		"activity:open:1",
		"aos:erroLua:bianqiang_niudan",
	} {
		got, ok := classifyOpcode25RPC(opcode25CommandForTest(command))
		if !ok || got != command {
			t.Errorf("command %q not classified as RPC: got %q ok %v", command, got, ok)
		}
	}
}

func TestOpcode25RejectsBinaryCombatAndMalformedRPC(t *testing.T) {
	// targetID=1, skillID=42, nonce length 0. Must remain binary SkillCast.
	combat := []byte{0, 0, 0, 1, 0, 0, 0, 42, 0, 0}
	bad := [][]byte{
		combat,
		nil,
		{0, 5, 'a', ':', 'b'},
		{0, 3, 'a', ':', 'b', 0},
		{0, 3, 0xff, ':', 'b'},
		{0, 3, 'a', ':', ' '},
		{0, 3, '1', '2', '3'},
	}
	for _, body := range bad {
		if got, ok := classifyOpcode25RPC(body); ok {
			t.Errorf("classified binary/malformed body as RPC: %q, bytes=%x", got, body)
		}
	}
}
