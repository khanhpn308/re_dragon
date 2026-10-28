package scenario

import (
	"context"
	"fmt"
	"log/slog"
	"math/rand"
	"sync"
	"time"

	"returnsaiyan/gameserver/tools/loadgen/internal/client"
	"returnsaiyan/gameserver/tools/loadgen/internal/metrics"
)

type CohortType string

const (
	CohortIdle   CohortType = "idle"
	CohortWorld  CohortType = "world"
	CohortCombat CohortType = "combat"
	CohortMenu   CohortType = "menu"
)

type Config struct {
	TargetAddr   string
	TotalCCU     int
	RampDuration time.Duration
	HoldDuration time.Duration
	Logger       *slog.Logger
}

type Runner struct {
	cfg       Config
	collector *metrics.Collector
	clients   []*client.SimulatedClient
}

func NewRunner(cfg Config, collector *metrics.Collector) *Runner {
	return &Runner{
		cfg:       cfg,
		collector: collector,
		clients:   make([]*client.SimulatedClient, 0, cfg.TotalCCU),
	}
}

// Run executes the full ramp-up and steady-state load generation cycle.
func (r *Runner) Run(ctx context.Context) error {
	r.cfg.Logger.Info("starting load generator scenario",
		slog.Int("total_ccu", r.cfg.TotalCCU),
		slog.Duration("ramp", r.cfg.RampDuration),
		slog.Duration("hold", r.cfg.HoldDuration),
		slog.String("target", r.cfg.TargetAddr),
	)

	// Step 1: Ramp up connections
	spawnInterval := time.Duration(0)
	if r.cfg.RampDuration > 0 && r.cfg.TotalCCU > 0 {
		spawnInterval = r.cfg.RampDuration / time.Duration(r.cfg.TotalCCU)
	}

	var wg sync.WaitGroup
	clientCtx, cancelClients := context.WithCancel(ctx)
	defer cancelClients()

	for i := 0; i < r.cfg.TotalCCU; i++ {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		clientID := i + 1
		username := fmt.Sprintf("bench_user_%d", clientID)
		cli := client.NewSimulatedClient(clientID, r.cfg.TargetAddr, username, "password123", r.collector, 5*time.Second)

		// Determine cohort per 5000 CCU specification: 40% idle, 30% world, 20% combat, 10% menu
		cohort := CohortIdle
		mod := clientID % 10
		if mod < 4 {
			cohort = CohortIdle // 40%
		} else if mod < 7 {
			cohort = CohortWorld // 30%
		} else if mod < 9 {
			cohort = CohortCombat // 20%
		} else {
			cohort = CohortMenu // 10%
		}

		if err := cli.Connect(); err != nil {
			r.cfg.Logger.Warn("client connect failed", slog.Int("id", clientID), slog.String("err", err.Error()))
			continue
		}

		if err := cli.Login(); err != nil {
			r.cfg.Logger.Warn("client login failed", slog.Int("id", clientID), slog.String("err", err.Error()))
			cli.Close()
			continue
		}

		if err := cli.EnterWorld(); err != nil {
			r.cfg.Logger.Warn("client enter world failed", slog.Int("id", clientID), slog.String("err", err.Error()))
			cli.Close()
			continue
		}

		r.clients = append(r.clients, cli)
		wg.Add(1)
		go r.runClientLoop(clientCtx, cli, cohort, &wg)

		if spawnInterval > 0 && spawnInterval < 50*time.Millisecond {
			time.Sleep(spawnInterval)
		} else if spawnInterval >= 50*time.Millisecond {
			time.Sleep(spawnInterval)
		}
	}

	r.cfg.Logger.Info("ramp-up complete, holding steady-state load",
		slog.Int64("active_ccu", r.collector.ActiveConns()),
		slog.Duration("hold_duration", r.cfg.HoldDuration),
	)

	// Hold duration
	select {
	case <-time.After(r.cfg.HoldDuration):
		r.cfg.Logger.Info("steady-state hold window expired, ramping down")
	case <-ctx.Done():
		r.cfg.Logger.Info("context cancelled, initiating shutdown")
	}

	cancelClients()
	wg.Wait()

	// Clean up client connections
	for _, c := range r.clients {
		c.Close()
	}

	r.cfg.Logger.Info("all load generator clients shut down cleanly")
	return nil
}

func (r *Runner) runClientLoop(ctx context.Context, cli *client.SimulatedClient, cohort CohortType, wg *sync.WaitGroup) {
	defer wg.Done()

	var interval time.Duration
	switch cohort {
	case CohortCombat:
		interval = 1200 * time.Millisecond // ~0.83 C2S/s per combat client
	case CohortWorld:
		interval = 1000 * time.Millisecond // 1.0 C2S/s
	case CohortMenu:
		interval = 5000 * time.Millisecond // 0.2 C2S/s
	case CohortIdle:
		interval = 20000 * time.Millisecond // 0.05 C2S/s
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	skills := []int32{101, 102, 103, 104}
	step := 0
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			step++
			nonce := fmt.Sprintf("nonce_%d_%d", cli.ID, step)

			switch cohort {
			case CohortCombat:
				target := int32(1001 + (step % 2))
				skillID := skills[step%len(skills)]
				_ = cli.SendSkillCast(target, skillID, nonce)

			case CohortWorld:
				// Move in small wander path
				x := float32(100 + (step%20)*5)
				y := float32(100 + (step%20)*5)
				_ = cli.SendMovement(x, y, 0, float32(step*15%360), nonce)

			case CohortMenu, CohortIdle:
				// Heartbeat
				_ = cli.SendHeartbeat()
			}

			// Add small 5-10% jitter to prevent artificial phase lock
			jitter := time.Duration(rand.Int63n(int64(interval / 10)))
			time.Sleep(jitter)
		}
	}
}
