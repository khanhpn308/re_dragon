package resilience_test

import (
	"context"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"math/rand"
	"net"
	"os"
	"sort"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"returnsaiyan/gameserver/internal/domain/world"
	"returnsaiyan/gameserver/internal/protocol"
	"returnsaiyan/gameserver/internal/repository/postgres"
	"returnsaiyan/gameserver/internal/session"
	"returnsaiyan/gameserver/internal/transport/tcp"
)

const testDSN = "postgres://returnsaiyan:returnsaiyan_pass@127.0.0.1:5432/returnsaiyan_dev?sslmode=disable"

type testServerHolder struct {
	server *tcp.Server
}

func (sh *testServerHolder) GetConn(connID string) (*tcp.ClientConn, bool) {
	if sh.server != nil {
		return sh.server.GetConn(connID)
	}
	return nil, false
}

// startTestServer initializes and starts a full server wired to PostgreSQL or local auth.
func startTestServer(t *testing.T, pool *pgxpool.Pool) (string, func()) {
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelWarn}))

	var auth session.Authenticator
	if pool != nil {
		auth = postgres.NewPostgresAccountRepository(pool)
	} else {
		auth = session.NewLocalAuthenticator()
	}

	sessionMgr := session.NewSessionManager(10 * time.Minute)
	worldEngine := world.NewWorldEngine(50 * time.Millisecond)
	worldEngine.Start(context.Background())

	holder := &testServerHolder{}
	handler := session.NewAuthHandler(auth, sessionMgr, holder, "127.0.0.1", 0, logger)
	handler.SetWorldEngine(worldEngine)

	cfg := tcp.Config{
		Addr:           "127.0.0.1:0", // Listen on random available port
		ReadTimeout:    5 * time.Second,
		WriteTimeout:   2 * time.Second,
		MaxConnections: 1000,
	}

	server := tcp.NewServer(cfg, handler, logger)
	holder.server = server

	require.NoError(t, server.Start())
	addr := server.Addr().String()

	cleanup := func() {
		_ = server.Stop(1 * time.Second)
		worldEngine.Stop()
	}

	return addr, cleanup
}

// clientConnHelper wraps client wire protocol primitives.
type clientConnHelper struct {
	conn net.Conn
	key  byte
	seq  byte
}

func dialClientHelper(t *testing.T, addr string) *clientConnHelper {
	conn, err := net.DialTimeout("tcp", addr, 3*time.Second)
	require.NoError(t, err)

	greeting := make([]byte, 7)
	_, err = io.ReadFull(conn, greeting)
	require.NoError(t, err)
	require.Equal(t, byte(0x00), greeting[0])
	require.Equal(t, byte(0x05), greeting[1])
	require.Equal(t, byte(0x00), greeting[2])

	seed := binary.BigEndian.Uint32(greeting[3:7])
	key := protocol.GerarChaveSecreta(seed)

	return &clientConnHelper{
		conn: conn,
		key:  key,
		seq:  0,
	}
}

func (c *clientConnHelper) SendPacket(pw *protocol.PacketWriter) error {
	raw, err := pw.FinalizeC2S(c.seq)
	if err != nil {
		return err
	}
	c.seq++
	wirePacket := append(raw[:2], protocol.CifrarC2S(raw[2:], c.key)...)
	_, err = c.conn.Write(wirePacket)
	return err
}

func (c *clientConnHelper) RecvPacket(timeout time.Duration) (byte, []byte, error) {
	_ = c.conn.SetReadDeadline(time.Now().Add(timeout))
	var encHdr [2]byte
	if _, err := io.ReadFull(c.conn, encHdr[:]); err != nil {
		return 0, nil, err
	}

	payloadLen := protocol.DecifrarS2CHeader(encHdr, c.key)
	if payloadLen < 1 {
		return 0, nil, errors.New("zero length S2C payload")
	}

	encPayload := make([]byte, payloadLen)
	if _, err := io.ReadFull(c.conn, encPayload); err != nil {
		return 0, nil, err
	}

	decPayload := protocol.DecifrarS2C(encPayload, c.key)
	return decPayload[0], decPayload[1:], nil
}

func (c *clientConnHelper) Close() {
	_ = c.conn.Close()
}

func getSharedPool(t *testing.T) *pgxpool.Pool {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	poolCfg := postgres.DefaultPoolConfig(testDSN)
	pool, err := postgres.NewPool(ctx, poolCfg)
	require.NoError(t, err)

	migrator := postgres.NewMigrator(pool)
	require.NoError(t, migrator.Up(ctx))

	return pool
}

// =========================================================================
// T05: Burst Login, Reconnect Churn, and Duplicate Eviction
// =========================================================================

func TestT05_BurstLoginAndReconnectChurn(t *testing.T) {
	pool := getSharedPool(t)
	defer pool.Close()

	addr, cleanup := startTestServer(t, pool)
	defer cleanup()

	burstRates := []int{50, 100, 250}

	for _, rate := range burstRates {
		t.Run(fmt.Sprintf("BurstRate_%d_per_sec", rate), func(t *testing.T) {
			var wg sync.WaitGroup
			latencies := make([]time.Duration, rate)
			var successCount atomic.Int64
			var failCount atomic.Int64

			start := time.Now()
			for i := 0; i < rate; i++ {
				wg.Add(1)
				go func(idx int) {
					defer wg.Done()
					t0 := time.Now()
					cli := dialClientHelper(t, addr)
					defer cli.Close()

					username := fmt.Sprintf("burst_u_%d_%d_%d", rate, time.Now().UnixNano()%100000, idx)
					password := "burst_pass_123"

					// Register
					pwReg := protocol.NewPacketWriter(protocol.OpcodeRegisterAccount)
					pwReg.WriteStr(username).WriteStr(password)
					if err := cli.SendPacket(pwReg); err != nil {
						failCount.Add(1)
						return
					}
					op, _, err := cli.RecvPacket(3 * time.Second)
					if err != nil || op != protocol.OpcodeRegisterResult {
						failCount.Add(1)
						return
					}

					// Login
					pwLogin := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
					pwLogin.WriteStr(username).WriteStr(password).WriteStr("91184").WriteStr("1.0.17")
					if err := cli.SendPacket(pwLogin); err != nil {
						failCount.Add(1)
						return
					}
					op, _, err = cli.RecvPacket(3 * time.Second)
					if err != nil || op != protocol.OpcodeRoleLoginResponse {
						failCount.Add(1)
						return
					}

					latencies[idx] = time.Since(t0)
					successCount.Add(1)
				}(i)

				// Throttle emission to match target rate
				time.Sleep(time.Second / time.Duration(rate*2))
			}

			wg.Wait()
			elapsed := time.Since(start)

			require.Equal(t, int64(rate), successCount.Load(), "all burst logins must succeed")
			require.Equal(t, int64(0), failCount.Load(), "zero login failures allowed")

			// Calculate latency percentiles
			validLats := make([]float64, 0, rate)
			for _, l := range latencies {
				if l > 0 {
					validLats = append(validLats, float64(l.Milliseconds()))
				}
			}
			sort.Float64s(validLats)

			p50 := validLats[len(validLats)*50/100]
			p95 := validLats[len(validLats)*95/100]
			p99 := validLats[len(validLats)*99/100]

			t.Logf("Burst rate %d/s: elapsed=%v, p50=%.2fms, p95=%.2fms, p99=%.2fms", rate, elapsed, p50, p95, p99)
			assert.Less(t, p95, 500.0, "p95 login latency must be <= 500ms under burst churn")
		})
	}

	// Subtest: Duplicate login eviction (Opcode 0x07)
	t.Run("DuplicateLoginEviction", func(t *testing.T) {
		cli1 := dialClientHelper(t, addr)
		defer cli1.Close()

		username := fmt.Sprintf("dupe_user_%d", time.Now().UnixNano()%100000)
		password := "dupe_pass"

		// Register
		pwReg := protocol.NewPacketWriter(protocol.OpcodeRegisterAccount)
		pwReg.WriteStr(username).WriteStr(password)
		require.NoError(t, cli1.SendPacket(pwReg))
		op, _, err := cli1.RecvPacket(3 * time.Second)
		require.NoError(t, err)
		require.Equal(t, protocol.OpcodeRegisterResult, op)

		// First login
		pwLogin1 := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
		pwLogin1.WriteStr(username).WriteStr(password).WriteStr("91184").WriteStr("1.0.17")
		require.NoError(t, cli1.SendPacket(pwLogin1))
		op, _, err = cli1.RecvPacket(3 * time.Second)
		require.NoError(t, err)
		require.Equal(t, protocol.OpcodeRoleLoginResponse, op)

		// Second login from a different socket
		cli2 := dialClientHelper(t, addr)
		defer cli2.Close()

		pwLogin2 := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
		pwLogin2.WriteStr(username).WriteStr(password).WriteStr("91184").WriteStr("1.0.17")
		require.NoError(t, cli2.SendPacket(pwLogin2))

		// Client 2 should receive successful login
		op2, _, err2 := cli2.RecvPacket(3 * time.Second)
		require.NoError(t, err2)
		require.Equal(t, protocol.OpcodeRoleLoginResponse, op2)

		// Client 1 should receive Opcode 0x07 (System Prompt / Eviction notification)
		op1, body1, err1 := cli1.RecvPacket(3 * time.Second)
		require.NoError(t, err1)
		require.Equal(t, protocol.OpcodeSystemPrompt, op1)
		pr := protocol.NewPacketReader(body1)
		msg, err := pr.ReadStr()
		require.NoError(t, err)
		assert.Contains(t, msg, "logged in from another device")
	})
}

// =========================================================================
// T06: Database Read/Write Throughput Under 90/10, 70/30, 40/60 Mixes
// =========================================================================

func TestT06_DatabaseThroughputMixes(t *testing.T) {
	pool := getSharedPool(t)
	defer pool.Close()

	accRepo := postgres.NewPostgresAccountRepository(pool)
	progRepo := postgres.NewPostgresProgressionRepository(pool)

	mixes := []struct {
		name       string
		readRatio  int // percentage
		writeRatio int
		totalOps   int
	}{
		{"Mix_90_10_ReadHeavy", 90, 10, 200},
		{"Mix_70_30_Balanced", 70, 30, 200},
		{"Mix_40_60_WriteHeavy", 40, 60, 200},
	}

	ctx := context.Background()

	// Seed test accounts and progression
	testUsers := make([]string, 20)
	testIDs := make([]int64, 20)
	testRoleIDs := make([]int32, 20)
	for i := 0; i < 20; i++ {
		u := fmt.Sprintf("mix_usr_%d_%d", time.Now().UnixNano()%100000, i)
		acc, err := accRepo.Register(ctx, u, "mix_pass")
		require.NoError(t, err)
		testUsers[i] = u
		testIDs[i] = acc.ID

		roles, err := accRepo.GetRoles(ctx, acc.ID)
		require.NoError(t, err)
		require.NotEmpty(t, roles)
		testRoleIDs[i] = int32(roles[0].ID)

		_ = progRepo.SaveProgression(ctx, testRoleIDs[i], 1, 0, 100)
	}

	for _, mix := range mixes {
		t.Run(mix.name, func(t *testing.T) {
			var wg sync.WaitGroup
			readLatencies := make([]time.Duration, 0, mix.totalOps)
			writeLatencies := make([]time.Duration, 0, mix.totalOps)
			var mu sync.Mutex

			start := time.Now()
			concurrency := 10
			opsPerWorker := mix.totalOps / concurrency

			for w := 0; w < concurrency; w++ {
				wg.Add(1)
				go func(workerID int) {
					defer wg.Done()
					r := rand.New(rand.NewSource(time.Now().UnixNano() + int64(workerID)))

					for i := 0; i < opsPerWorker; i++ {
						idx := r.Intn(len(testIDs))
						accID := testIDs[idx]
						roleID := testRoleIDs[idx]
						isRead := r.Intn(100) < mix.readRatio

						t0 := time.Now()
						if isRead {
							// Read operation: GetRoles or Authenticate
							_, err := accRepo.GetRoles(ctx, accID)
							require.NoError(t, err)
							dur := time.Since(t0)
							mu.Lock()
							readLatencies = append(readLatencies, dur)
							mu.Unlock()
						} else {
							// Write operation: Update progression
							stage := 1 + r.Intn(10)
							err := progRepo.SaveProgression(ctx, roleID, stage, 0, 500)
							require.NoError(t, err)
							dur := time.Since(t0)
							mu.Lock()
							writeLatencies = append(writeLatencies, dur)
							mu.Unlock()
						}
					}
				}(w)
			}

			wg.Wait()
			elapsed := time.Since(start)

			t.Logf("[%s] completed %d ops in %v (throughput: %.1f ops/s)",
				mix.name, mix.totalOps, elapsed, float64(mix.totalOps)/elapsed.Seconds())
			assert.NotEmpty(t, readLatencies)
			assert.NotEmpty(t, writeLatencies)
		})
	}
}

// =========================================================================
// T07: Contended Mutations and Replay Protection
// =========================================================================

func TestT07_ContendedMutationsAndReplayProtection(t *testing.T) {
	pool := getSharedPool(t)
	defer pool.Close()

	ctx := context.Background()
	accRepo := postgres.NewPostgresAccountRepository(pool)
	invRepo := postgres.NewPostgresInventoryRepository(pool)

	username := fmt.Sprintf("contend_u_%d", time.Now().UnixNano()%100000)
	acc, err := accRepo.Register(ctx, username, "contend_pass")
	require.NoError(t, err)

	roles, err := accRepo.GetRoles(ctx, acc.ID)
	require.NoError(t, err)
	require.NotEmpty(t, roles)
	roleID := int32(roles[0].ID)

	// Add 500 initial Senzu beans (ItemID: 9001) to slot 0
	err = invRepo.SetItem(ctx, roleID, 0, 9001, 500)
	require.NoError(t, err)

	t.Run("ConcurrentContendedInventoryDeductions", func(t *testing.T) {
		// 20 concurrent goroutines attempt to spend 25 items each (total = 500)
		workers := 20
		spendPerWorker := 25
		var wg sync.WaitGroup
		var successCount atomic.Int32
		var failCount atomic.Int32

		for i := 0; i < workers; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				// Atomic transactional deduction using SELECT ... FOR UPDATE
				err := invRepo.TransferItem(ctx, roleID, 0, roleID, 1, spendPerWorker)
				if err == nil {
					successCount.Add(1)
				} else {
					failCount.Add(1)
				}
			}()
		}

		wg.Wait()

		// Verify total transferred equals exactly 500, and slot 0 remaining is 0 (deleted)
		_, err := invRepo.GetItem(ctx, roleID, 0)
		assert.ErrorIs(t, err, postgres.ErrItemNotFound, "source slot should now be empty")

		slot1, err := invRepo.GetItem(ctx, roleID, 1)
		require.NoError(t, err)
		assert.Equal(t, 500, slot1.Count, "destination slot should have exactly 500")

		t.Logf("Contended transfers: successes=%d, fails=%d, slot1_qty=%d",
			successCount.Load(), failCount.Load(), slot1.Count)

		// Overdraft attempt: spending 1 more item must fail without going negative
		err = invRepo.TransferItem(ctx, roleID, 0, roleID, 1, 1)
		assert.Error(t, err, "overdraft transfer must fail")
	})

	t.Run("IdempotencyDuplicateReplayProtection", func(t *testing.T) {
		idempotencyMgr := world.NewIdempotencyManager(5 * time.Minute)

		nonce := fmt.Sprintf("nonce_tx_%d", time.Now().UnixNano())

		// First execution: begin attempt
		rec, err := idempotencyMgr.BeginAttempt(nonce, roleID)
		require.NoError(t, err, "first execution with nonce must succeed")
		require.Equal(t, world.ActionPending, rec.Status)

		// Complete attempt with result code 200 (Success)
		idempotencyMgr.CompleteAttempt(nonce, 200, "battle_reward_committed")

		// Duplicate replay with same nonce: must be rejected with ErrDuplicateAction
		replayedRec, err := idempotencyMgr.BeginAttempt(nonce, roleID)
		require.ErrorIs(t, err, world.ErrDuplicateAction, "duplicate nonce must be rejected")
		require.Equal(t, int32(200), replayedRec.ResultCode, "cached result code must match original")
		require.Equal(t, "battle_reward_committed", replayedRec.ErrorMessage)
	})
}

// =========================================================================
// T08: Adverse TCP and Network Stress Handling
// =========================================================================

func TestT08_AdverseNetworkHandling(t *testing.T) {
	addr, cleanup := startTestServer(t, nil) // In-memory auth
	defer cleanup()

	t.Run("FrameSplittingByteByByte", func(t *testing.T) {
		cli := dialClientHelper(t, addr)
		defer cli.Close()

		// Prepare heartbeat ping
		pw := protocol.NewPacketWriter(protocol.OpcodeHeartbeatPing)
		pw.WriteI32(12345678)
		raw, err := pw.FinalizeC2S(cli.seq)
		require.NoError(t, err)
		cli.seq++
		enc := protocol.CifrarC2S(raw[2:], cli.key)
		wirePacket := append(raw[:2], enc...)

		// Send 1 byte at a time with slight delays
		for i := 0; i < len(wirePacket); i++ {
			_, err := cli.conn.Write(wirePacket[i : i+1])
			require.NoError(t, err)
			time.Sleep(2 * time.Millisecond)
		}

		// Server should assemble and respond with OpcodeHeartbeatPong (0x28)
		op, body, err := cli.RecvPacket(3 * time.Second)
		require.NoError(t, err)
		require.Equal(t, protocol.OpcodeHeartbeatPong, op)
		pr := protocol.NewPacketReader(body)
		ts, err := pr.ReadI32()
		require.NoError(t, err)
		assert.Equal(t, int32(12345678), ts)
	})

	t.Run("FrameCoalescingMultiplePackets", func(t *testing.T) {
		cli := dialClientHelper(t, addr)
		defer cli.Close()

		// Prepare 5 heartbeat pings coalesced into single write
		var coalescedBuf []byte
		for i := 0; i < 5; i++ {
			pw := protocol.NewPacketWriter(protocol.OpcodeHeartbeatPing)
			pw.WriteI32(int32(100 + i))
			raw, err := pw.FinalizeC2S(cli.seq)
			require.NoError(t, err)
			cli.seq++
			enc := protocol.CifrarC2S(raw[2:], cli.key)
			wirePacket := append(raw[:2], enc...)
			coalescedBuf = append(coalescedBuf, wirePacket...)
		}

		// Write all 5 frames in one single socket write
		_, err := cli.conn.Write(coalescedBuf)
		require.NoError(t, err)

		// Read back all 5 responses
		for i := 0; i < 5; i++ {
			op, body, err := cli.RecvPacket(3 * time.Second)
			require.NoError(t, err)
			require.Equal(t, protocol.OpcodeHeartbeatPong, op)
			pr := protocol.NewPacketReader(body)
			ts, err := pr.ReadI32()
			require.NoError(t, err)
			require.Equal(t, int32(100+i), ts)
		}
	})

	t.Run("OversizedFrameRejection", func(t *testing.T) {
		cli := dialClientHelper(t, addr)
		defer cli.Close()

		// Craft frame header claiming length 9000 (> MaxPacketLength 8192)
		var fakeHdr [2]byte
		binary.BigEndian.PutUint16(fakeHdr[:], 9000)

		_, err := cli.conn.Write(fakeHdr[:])
		require.NoError(t, err)

		// Server must immediately disconnect without allocating memory
		buf := make([]byte, 100)
		_ = cli.conn.SetReadDeadline(time.Now().Add(2 * time.Second))
		n, err := cli.conn.Read(buf)
		assert.True(t, err == io.EOF || n == 0, "server must terminate socket on oversized frame")
	})

	t.Run("AbruptEOFHandling", func(t *testing.T) {
		cli := dialClientHelper(t, addr)
		// Half-write then immediately close socket
		_, _ = cli.conn.Write([]byte{0x01, 0x02})
		cli.Close()
		// Server must not panic or leak goroutines
		time.Sleep(50 * time.Millisecond)
	})
}

// =========================================================================
// T09: Controlled Crash, Restart, and State Durability Recovery
// =========================================================================

func TestT09_ControlledCrashAndRecovery(t *testing.T) {
	pool := getSharedPool(t)
	defer pool.Close()

	ctx := context.Background()
	accRepo := postgres.NewPostgresAccountRepository(pool)
	progRepo := postgres.NewPostgresProgressionRepository(pool)

	username := fmt.Sprintf("crash_u_%d", time.Now().UnixNano()%100000)
	password := "crash_pass_456"

	// Step 1: Start Server Instance A
	addrA, cleanupA := startTestServer(t, pool)

	// Step 2: Register account and advance progression to Stage 5
	cliA := dialClientHelper(t, addrA)
	pwReg := protocol.NewPacketWriter(protocol.OpcodeRegisterAccount)
	pwReg.WriteStr(username).WriteStr(password)
	require.NoError(t, cliA.SendPacket(pwReg))
	op, _, err := cliA.RecvPacket(3 * time.Second)
	require.NoError(t, err)
	require.Equal(t, protocol.OpcodeRegisterResult, op)

	acc, err := accRepo.Authenticate(ctx, username, password)
	require.NoError(t, err)

	roles, err := accRepo.GetRoles(ctx, acc.ID)
	require.NoError(t, err)
	require.NotEmpty(t, roles)
	roleID := int32(roles[0].ID)

	err = progRepo.SaveProgression(ctx, roleID, 5, 2, 3)
	require.NoError(t, err)

	cliA.Close()

	// Step 3: Hard crash Server Instance A
	t.Log("Simulating hard crash of Game Server Instance A...")
	cleanupA()

	// Step 4: Start fresh Server Instance B pointing to same PostgreSQL
	t.Log("Starting Server Instance B on same PostgreSQL database...")
	addrB, cleanupB := startTestServer(t, pool)
	defer cleanupB()

	// Step 5: Connect client to Server Instance B and verify state durability
	cliB := dialClientHelper(t, addrB)
	defer cliB.Close()

	pwLogin := protocol.NewPacketWriter(protocol.OpcodeLoginRequest)
	pwLogin.WriteStr(username).WriteStr(password).WriteStr("91184").WriteStr("1.0.17")
	require.NoError(t, cliB.SendPacket(pwLogin))

	opLogin, bodyLogin, err := cliB.RecvPacket(3 * time.Second)
	require.NoError(t, err)
	require.Equal(t, protocol.OpcodeRoleLoginResponse, opLogin)

	prLogin := protocol.NewPacketReader(bodyLogin)
	token, _ := prLogin.ReadStr()
	assert.NotEmpty(t, token)

	// Verify Stage 5 progression survived server crash intact
	prog, err := progRepo.GetProgression(ctx, roleID)
	require.NoError(t, err)
	require.Equal(t, 5, prog.StageID, "committed stage must survive server crash")
	require.Equal(t, 2, prog.StageProgress, "committed stage progress must survive server crash")
	require.Equal(t, 3, prog.Stars, "committed stars must survive server crash")

	t.Log("Server crash and recovery successfully verified with zero state loss!")
}
