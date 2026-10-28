package metrics_test

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"

	"returnsaiyan/gameserver/tools/loadgen/internal/metrics"
)

func TestCollector_PercentilesAndCounters(t *testing.T) {
	c := metrics.NewCollector()

	c.IncActiveConns()
	c.IncActiveConns()
	assert.Equal(t, int64(2), c.ActiveConns())
	assert.Equal(t, int64(2), c.TotalConns())

	c.DecActiveConns()
	assert.Equal(t, int64(1), c.ActiveConns())

	// Record latency samples for Opcode 0x20
	// 10 samples: 10ms, 20ms, 30ms, 40ms, 50ms, 60ms, 70ms, 80ms, 90ms, 100ms
	for i := 1; i <= 10; i++ {
		c.RecordAction(0x20, time.Duration(i*10)*time.Millisecond, true, "")
	}

	// 1 error
	c.RecordAction(0x20, 50*time.Millisecond, false, "timeout")

	c.RecordDBWait(5 * time.Millisecond)
	c.RecordSend(100)
	c.RecordRecv(200)

	report := c.GenerateReport()
	assert.Equal(t, int64(1), report.ActiveConns)
	assert.Equal(t, int64(1), report.PacketsSent)
	assert.Equal(t, int64(1), report.PacketsRecv)
	assert.Equal(t, int64(1), report.Errors["timeout"])

	// Check overall summary
	assert.Equal(t, int64(10), report.OverallSummary.Count)
	assert.Equal(t, 10.0, report.OverallSummary.MinMs)
	assert.Equal(t, 100.0, report.OverallSummary.MaxMs)
	assert.Equal(t, 60.0, report.OverallSummary.P50Ms) // index 5 -> 60ms
	assert.Equal(t, 100.0, report.OverallSummary.P95Ms)
	assert.Equal(t, 100.0, report.OverallSummary.P99Ms)
	assert.InDelta(t, 90.9, report.OverallSummary.SuccessRate, 0.5)

	// Check DB wait summary
	assert.Equal(t, int64(1), report.DBWaitSummary.Count)
	assert.Equal(t, 5.0, report.DBWaitSummary.P50Ms)
}
