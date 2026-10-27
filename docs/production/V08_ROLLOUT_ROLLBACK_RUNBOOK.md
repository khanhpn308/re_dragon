# RE Dragon v0.8 — Safe Rollout & Rollback Runbook

**Target Version:** v0.8.0  
**Repository:** `khanhpn308/re_dragon`  
**Production Workspace:** `/home/khanh/returnsaiyan-re`  
**Production Active Project ID:** Check via `python3 -m re_harness.quota_watchdog status`  
**Safety Classification:** Level 1 Mission Critical — Strict Fail-Closed

---

## 1. Safety Principles & Invariants

1. **Zero Hot-Patching**: Never modify running processes or database files while Watchdog or Agent CLI is in-flight.
2. **Safe Checkpoint Cutover**: Upgrades only take place when Watchdog is between turns (e.g. status `WAIT`, `YIELD`, `WAIT_QUOTA`, or cleanly stopped).
3. **Data Preservation**: Under no circumstances shall `.re_harness_mvp/state.sqlite3` be wiped, dropped, or corrupted. All completed tasks (`status='VERIFIED'`) and project acceptance markers must remain intact.
4. **Independent Audit Pre-condition**: No production deployment may proceed without 100% passing automated regression tests and independent subagent review.

---

## 2. Pre-Rollout Verification Checklist

Before initiating any deployment:
- [ ] Feature branch `feature/v08-autonomous-reliability-recovery` passes all 219 unit tests:
  ```bash
  python3 -m unittest discover -s tests -v
  ```
- [ ] Bytecode compilation has zero errors:
  ```bash
  python -m compileall -q re_harness tests
  ```
- [ ] Independent reviewer (`re-dragon-reviewer`) has issued `APPROVE` verdict on primary evidence.
- [ ] GitHub Actions CI workflow (`watchdog-pr-checks.yml`) passes on Python 3.11 and 3.13.

---

## 3. Production Rollout Procedure

### Step 1: Inspect Live State & Pinned Project
In the production workspace:
```bash
cd /home/khanh/returnsaiyan-re
./dragon status
```
Confirm:
- Pinned `project_id` matches the active V1 production charter.
- Record the current turn count, active task, and conversation ID.

### Step 2: Create Pre-Rollout Snapshot Backup with WAL Checkpoint
Create a consistent, verified snapshot of the SQLite database and state files using the v0.8 WAL-truncating backup tool:
```bash
BACKUP_DIR="$HOME/backups/re-dragon-v08-rollout-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Execute atomic SQLite backup with PRAGMA wal_checkpoint(TRUNCATE) and manifest generation
python3 -m re_harness.backup_util backup \
  --workspace /home/khanh/returnsaiyan-re \
  --backup-dir "$BACKUP_DIR" \
  --label pre_v08_rollout

echo "Atomic backup created and verified in: $BACKUP_DIR"
```
Verify the generated `backup-manifest.json` contains:
- Valid SHA-256 for `state.sqlite3`
- Current Git commit SHA (`git rev-parse HEAD`)
- Verified `quota-watchdog.json`

### Step 3: Graceful Drain & Stop of Active Production Session
Do NOT abruptly kill the in-flight process! First, issue a graceful drain to allow any active agent turn to complete and checkpoint:
```bash
cd /home/khanh/returnsaiyan-re
./dragon drain 120
```
When `drain` reports `"status": "PAUSED"`, stop the tmux processes:
```bash
./dragon stop
```
Verify all processes are cleanly stopped:
```bash
tmux has-session -t re-dragon-quota-watchdog 2>/dev/null && echo "ERROR: session still active" || echo "Cleanly stopped"
pgrep -f "re_harness" || echo "Zero background harness processes"
```

### Step 4: Apply v0.8 Release
Merge `feature/v08-autonomous-reliability-recovery` into `main` (or pull on production workspace):
```bash
cd /home/khanh/returnsaiyan-re
git fetch origin
git checkout main
git merge --ff-only origin/main
```

### Step 5: Verify Schema & Run Preflight Tests
Run offline regression tests on production python environment:
```bash
python3 -m unittest discover -s tests
```
Initialize the new incident journal:
```bash
python3 -c "from re_harness import incidents; incidents.connection('.')"
ls -la .re_harness/incidents.sqlite3
```

### Step 6: Restart Autonomous Watchdog
Resume with the exact pinned production project ID:
```bash
./dragon resume
```
Verify Watchdog started in tmux:
```bash
./dragon status
```

### Step 7: Post-Rollout Smoke Test via Telegram
Open Telegram and issue:
1. `/status` — Confirm state is `AGENT_RUNNING` or `CONTINUE` with pinned project ID.
2. `/incidents` — Verify incident journal is accessible.
3. `/progress` — Verify verified task count matches pre-rollout snapshot.

---

## 4. Rollback Procedure

If any anomaly occurs (e.g. repeated crashes, database lock deadlock, unrecognized state):

### Step 1: Immediate Drain & Stop
```bash
cd /home/khanh/returnsaiyan-re
./dragon stop --force
tmux kill-session -t re-dragon-quota-watchdog 2>/dev/null || true
```

### Step 2: Restore Pre-Rollout Code & Checkpoints
```bash
cd /home/khanh/returnsaiyan-re

# Check out the recorded pre-rollout commit SHA from backup-manifest.json
PRE_SHA=$(jq -r .git_commit_sha "$BACKUP_DIR"/backup_*/backup-manifest.json)
git checkout "$PRE_SHA"

# Safely restore and verify SQLite database and state files
SNAPSHOT_DIR=$(ls -d "$BACKUP_DIR"/backup_* | head -n 1)
python3 -m re_harness.backup_util restore \
  --backup-snapshot "$SNAPSHOT_DIR" \
  --workspace /home/khanh/returnsaiyan-re
```

### Step 3: Restart Legacy Watchdog
```bash
./dragon resume
./dragon status
```
Verify via Telegram `/status` that the original checkpoint has resumed.
