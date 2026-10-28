package metrics

import (
	"fmt"
	"math"
	"sort"
	"sync"
	"sync/atomic"
	"time"
)

// MetricSample records a single latency observation.
type MetricSample struct {
	Opcode   byte
	Duration time.Duration
	Success  bool
	ErrType  string
}

// LatencySummary contains percentiles and counts.
type LatencySummary struct {
	Count       int64   `json:"count"`
	MinMs       float64 `json:"min_ms"`
	P50Ms       float64 `json:"p50_ms"`
	P95Ms       float64 `json:"p95_ms"`
	P99Ms       float64 `json:"p99_ms"`
	MaxMs       float64 `json:"max_ms"`
	MeanMs      float64 `json:"mean_ms"`
	ErrorCount  int64   `json:"error_count"`
	SuccessRate float64 `json:"success_rate"`
}

// Collector tracks load test metrics with thread-safe counters and high-resolution latency buffers.
type Collector struct {
	mu            sync.Mutex
	startTime     time.Time
	activeConns   int64
	totalConns    int64
	connErrors    int64
	packetsSent   int64
	packetsRecv   int64
	bytesSent     int64
	bytesRecv     int64
	samples       map[byte][]time.Duration
	errorCounts   map[string]int64
	dbWaitSamples []time.Duration
}

func NewCollector() *Collector {
	return &Collector{
		startTime:   time.Now().UTC(),
		samples:     make(map[byte][]time.Duration),
		errorCounts: make(map[string]int64),
	}
}

func (c *Collector) IncActiveConns() {
	atomic.AddInt64(&c.activeConns, 1)
	atomic.AddInt64(&c.totalConns, 1)
}

func (c *Collector) DecActiveConns() {
	atomic.AddInt64(&c.activeConns, -1)
}

func (c *Collector) IncConnErrors() {
	atomic.AddInt64(&c.connErrors, 1)
}

func (c *Collector) ActiveConns() int64 {
	return atomic.LoadInt64(&c.activeConns)
}

func (c *Collector) TotalConns() int64 {
	return atomic.LoadInt64(&c.totalConns)
}

func (c *Collector) RecordSend(bytes int) {
	atomic.AddInt64(&c.packetsSent, 1)
	atomic.AddInt64(&c.bytesSent, int64(bytes))
}

func (c *Collector) RecordRecv(bytes int) {
	atomic.AddInt64(&c.packetsRecv, 1)
	atomic.AddInt64(&c.bytesRecv, int64(bytes))
}

func (c *Collector) RecordAction(opcode byte, d time.Duration, success bool, errType string) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if success {
		c.samples[opcode] = append(c.samples[opcode], d)
	} else {
		if errType == "" {
			errType = "unknown"
		}
		c.errorCounts[errType]++
	}
}

func (c *Collector) RecordDBWait(d time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.dbWaitSamples = append(c.dbWaitSamples, d)
}

func computeSummary(durations []time.Duration, errors int64) LatencySummary {
	n := len(durations)
	if n == 0 {
		return LatencySummary{
			ErrorCount:  errors,
			SuccessRate: 0,
		}
	}

	sort.Slice(durations, func(i, j int) bool {
		return durations[i] < durations[j]
	})

	var sum float64
	for _, d := range durations {
		sum += float64(d.Microseconds()) / 1000.0
	}

	minMs := float64(durations[0].Microseconds()) / 1000.0
	maxMs := float64(durations[n-1].Microseconds()) / 1000.0
	meanMs := sum / float64(n)

	p50Index := int(math.Floor(float64(n) * 0.50))
	p95Index := int(math.Floor(float64(n) * 0.95))
	p99Index := int(math.Floor(float64(n) * 0.99))

	if p50Index >= n {
		p50Index = n - 1
	}
	if p95Index >= n {
		p95Index = n - 1
	}
	if p99Index >= n {
		p99Index = n - 1
	}

	total := int64(n) + errors
	successRate := float64(n) / float64(total) * 100.0

	return LatencySummary{
		Count:       int64(n),
		MinMs:       minMs,
		P50Ms:       float64(durations[p50Index].Microseconds()) / 1000.0,
		P95Ms:       float64(durations[p95Index].Microseconds()) / 1000.0,
		P99Ms:       float64(durations[p99Index].Microseconds()) / 1000.0,
		MaxMs:       maxMs,
		MeanMs:      meanMs,
		ErrorCount:  errors,
		SuccessRate: successRate,
	}
}

// Snapshot generates a complete report of current metrics.
type Report struct {
	DurationSeconds       float64                   `json:"duration_seconds"`
	ActiveConns           int64                     `json:"active_conns"`
	TotalConns            int64                     `json:"total_conns"`
	ConnErrors            int64                     `json:"conn_errors"`
	PacketsSent           int64                     `json:"packets_sent"`
	PacketsRecv           int64                     `json:"packets_recv"`
	OfferedThroughputC2S  float64                   `json:"offered_c2s_per_sec"`
	AchievedThroughputS2C float64                   `json:"achieved_s2c_per_sec"`
	OpcodeSummaries       map[string]LatencySummary `json:"opcode_summaries"`
	OverallSummary        LatencySummary            `json:"overall_summary"`
	DBWaitSummary         LatencySummary            `json:"db_wait_summary"`
	Errors                map[string]int64          `json:"errors"`
}

func (c *Collector) GenerateReport() Report {
	c.mu.Lock()
	defer c.mu.Unlock()

	duration := time.Since(c.startTime).Seconds()
	if duration <= 0 {
		duration = 0.001
	}

	var allSamples []time.Duration
	var totalErrors int64
	for _, errCount := range c.errorCounts {
		totalErrors += errCount
	}

	summaries := make(map[string]LatencySummary)
	for op, samples := range c.samples {
		allSamples = append(allSamples, samples...)
		summaries[fmt.Sprintf("0x%02X", op)] = computeSummary(samples, 0)
	}

	overall := computeSummary(allSamples, totalErrors)
	dbWait := computeSummary(c.dbWaitSamples, 0)

	errCopy := make(map[string]int64)
	for k, v := range c.errorCounts {
		errCopy[k] = v
	}

	sent := atomic.LoadInt64(&c.packetsSent)
	recv := atomic.LoadInt64(&c.packetsRecv)

	return Report{
		DurationSeconds:       duration,
		ActiveConns:           atomic.LoadInt64(&c.activeConns),
		TotalConns:            atomic.LoadInt64(&c.totalConns),
		ConnErrors:            atomic.LoadInt64(&c.connErrors),
		PacketsSent:           sent,
		PacketsRecv:           recv,
		OfferedThroughputC2S:  float64(sent) / duration,
		AchievedThroughputS2C: float64(recv) / duration,
		OpcodeSummaries:       summaries,
		OverallSummary:        overall,
		DBWaitSummary:         dbWait,
		Errors:                errCopy,
	}
}
