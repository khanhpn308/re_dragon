package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"returnsaiyan/gameserver/tools/loadgen/internal/metrics"
	"returnsaiyan/gameserver/tools/loadgen/internal/scenario"
)

func isSafeTarget(addr string) bool {
	host, _, err := net.SplitHostPort(addr)
	if err != nil {
		host = addr
	}

	ip := net.ParseIP(host)
	if ip == nil {
		return strings.EqualFold(host, "localhost")
	}

	return ip.IsLoopback() || ip.IsPrivate()
}

func main() {
	target := flag.String("target", "127.0.0.1:30001", "Target TCP server address (must be loopback or RFC1918 private)")
	ccu := flag.Int("ccu", 100, "Target concurrent clients (CCU)")
	ramp := flag.Duration("ramp", 5*time.Second, "Ramp-up duration")
	duration := flag.Duration("duration", 15*time.Second, "Steady-state hold duration")
	scenarioName := flag.String("scenario", "T01-smoke", "Test scenario identifier (T01-smoke, T02-ramp, T03-nominal, T04-soak)")
	outputFile := flag.String("output", "", "Optional path to export JSON metrics report")
	flag.Parse()

	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	// Safe target allowlist enforcement
	if !isSafeTarget(*target) {
		logger.Error("target address rejected: load generator only permits loopback or RFC1918 staging addresses",
			slog.String("target", *target),
		)
		os.Exit(1)
	}

	collector := metrics.NewCollector()
	runner := scenario.NewRunner(scenario.Config{
		TargetAddr:   *target,
		TotalCCU:     *ccu,
		RampDuration: *ramp,
		HoldDuration: *duration,
		Logger:       logger,
	}, collector)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-sigCh
		logger.Info("termination signal caught, cancelling load generation")
		cancel()
	}()

	start := time.Now()
	if err := runner.Run(ctx); err != nil && err != context.Canceled {
		logger.Error("load generation error", slog.String("error", err.Error()))
	}
	elapsed := time.Since(start)

	report := collector.GenerateReport()

	logger.Info("load test completed",
		slog.String("scenario", *scenarioName),
		slog.Duration("elapsed", elapsed),
		slog.Int64("total_conns", report.TotalConns),
		slog.Int64("active_conns", report.ActiveConns),
		slog.Int64("conn_errors", report.ConnErrors),
		slog.Float64("offered_c2s_s", report.OfferedThroughputC2S),
		slog.Float64("achieved_s2c_s", report.AchievedThroughputS2C),
		slog.Float64("overall_p50_ms", report.OverallSummary.P50Ms),
		slog.Float64("overall_p95_ms", report.OverallSummary.P95Ms),
		slog.Float64("overall_p99_ms", report.OverallSummary.P99Ms),
		slog.Float64("success_rate", report.OverallSummary.SuccessRate),
	)

	if *outputFile != "" {
		data, err := json.MarshalIndent(report, "", "  ")
		if err != nil {
			logger.Error("failed marshaling metrics report", slog.String("error", err.Error()))
		} else if err := os.WriteFile(*outputFile, data, 0644); err != nil {
			logger.Error("failed writing report file", slog.String("file", *outputFile), slog.String("error", err.Error()))
		} else {
			logger.Info("exported metrics report to file", slog.String("file", *outputFile))
		}
	} else {
		data, _ := json.MarshalIndent(report, "", "  ")
		fmt.Println(string(data))
	}
}
