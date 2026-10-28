package protocol

// Protocol opcode constants for ReturnSaiyan network protocol.
const (
	// Authentication and Gateway opcodes
	OpcodeLoginRequest         byte = 0x00 // C2S: Account login request
	OpcodeMsgBoxNotice         byte = 0x00 // S2C: Server broadcast / update notice
	OpcodeRoleLoginResponse    byte = 0x01 // S2C: Role list and gateway session response
	OpcodeAccountInfo          byte = 0x04 // S2C: Account token and credential validation
	OpcodeServerRedirect       byte = 0x05 // S2C: Server redirection host
	OpcodeSystemPrompt         byte = 0x07 // S2C: System popup notification / error prompt
	OpcodeChangePasswordResult byte = 0x08 // S2C: Password change result
	OpcodeRegisterAccount      byte = 0x09 // C2S: Account registration request
	OpcodeRegisterResult       byte = 0x0A // S2C: Account registration response

	// Gameplay and World state opcodes
	OpcodePlayerStatsSync byte = 0x10 // S2C: Player attributes and stage progress
	OpcodeEntitySpawn     byte = 0x12 // S2C: Entity map zone coordinates
	OpcodeEntityMoveSync  byte = 0x20 // C2S/S2C: Movement synchronization
	OpcodeBattleUpdate    byte = 0x21 // S2C: Battle state and effect updates
	OpcodeSkillCast       byte = 0x25 // C2S/S2C: Skill invocation event
	OpcodeResourceSync    byte = 0x26 // S2C: Resource asset manifest metadata
	OpcodeHeartbeatPing   byte = 0x27 // C2S: Heartbeat ping
	OpcodeHeartbeatPong   byte = 0x28 // S2C: Heartbeat pong
	OpcodeChatMessage     byte = 0x29 // C2S/S2C: Chat message update
	OpcodeInventoryUpdate byte = 0x2A // S2C: Inventory slot items
	OpcodeQuestUpdate     byte = 0x2B // S2C: Quest objectives
	OpcodeGuildUpdate     byte = 0x2C // S2C: Guild member info
	OpcodeActionNotify    byte = 0x2D // S2C: Special action notify
	OpcodeActionConfirm   byte = 0x2E // S2C: Action status code
	OpcodeMailUpdate      byte = 0x2F // S2C: Mailbox attachments
	OpcodePartyUpdate     byte = 0x30 // S2C: Party and team state

	// World Enter and Server Select
	OpcodeEnterWorld byte = 0x50 // C2S: Select character and enter game world
)
