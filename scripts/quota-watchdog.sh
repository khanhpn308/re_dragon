#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="re-dragon-quota-watchdog"
ACTION="${1:-status}"
MODE="${RE_DRAGON_AGENT_MODE:-auto}"

case "$ACTION" in
  start)
    command -v agy >/dev/null || { echo "Missing authenticated agy CLI" >&2; exit 1; }
    command -v tmux >/dev/null || { echo "Install tmux: sudo apt install tmux" >&2; exit 1; }
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "Quota Watchdog already running"; exit 0
    fi
    cmd=(python3 -m re_harness.quota_watchdog run --workspace "$ROOT" --mode "$MODE")
    if [[ -n "${2:-}" ]]; then cmd+=(--conversation "$2"); fi
    if [[ -n "${3:-${RE_DRAGON_PROJECT_ID:-}}" ]]; then cmd+=(--project-id "${3:-$RE_DRAGON_PROJECT_ID}"); fi
    if [[ -n "${RE_DRAGON_HARNESS_STATE_DIR:-}" ]]; then cmd+=(--harness-state-dir "$RE_DRAGON_HARNESS_STATE_DIR"); fi
    printf -v quoted '%q ' "${cmd[@]}"
    tmux new-session -d -s "$SESSION" -c "$ROOT" "$quoted"
    echo "Quota Watchdog started in tmux. Use: bash scripts/quota-watchdog.sh status"
    ;;
  status)
    (cd "$ROOT" && python3 -m re_harness.quota_watchdog status --workspace "$ROOT")
    if command -v tmux >/dev/null && tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "tmux background session: RUNNING"
    else
      echo "tmux background session: STOPPED"
    fi
    ;;
  logs)
    if [[ -f "$ROOT/.re_harness/quota-watchdog.log" ]]; then
      tail -n 40 "$ROOT/.re_harness/quota-watchdog.log"
    else echo "No watchdog log"; fi
    ;;
  drain)
    (cd "$ROOT" && python3 -m re_harness.quota_watchdog drain --workspace "$ROOT" --timeout "${2:-120}")
    ;;
  stop)
    if [[ "${2:-}" == "--force" ]]; then
      if command -v tmux >/dev/null && tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux kill-session -t "$SESSION"
      fi
      echo "Force stopped."
    else
      echo "Initiating graceful drain (waiting for in-flight turn to checkpoint)..."
      (cd "$ROOT" && python3 -m re_harness.quota_watchdog drain --workspace "$ROOT" --timeout "${2:-120}") || {
        echo "Drain timed out or failed. Use 'stop --force' if you must kill immediately." >&2
        exit 1
      }
      sleep 1
      if command -v tmux >/dev/null && tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux kill-session -t "$SESSION" 2>/dev/null || true
      fi
      echo "Gracefully stopped. State and checkpoints are safely preserved."
    fi
    ;;
  reset)
    if command -v tmux >/dev/null && tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "Stop running watcher before rearming" >&2; exit 1
    fi
    args=(python3 -m re_harness.quota_watchdog reset --workspace "$ROOT")
    if [[ -n "${2:-}" ]]; then args+=(--conversation "$2"); fi
    if [[ -n "${3:-${RE_DRAGON_PROJECT_ID:-}}" ]]; then args+=(--project-id "${3:-$RE_DRAGON_PROJECT_ID}"); fi
    (cd "$ROOT" && "${args[@]}")
    echo "Rearmed. Start watchdog again after resolving the blocker."
    ;;
  once)
    (cd "$ROOT" && python3 -m re_harness.quota_watchdog once --workspace "$ROOT" --mode "$MODE")
    ;;
  *)
    echo "Usage: bash scripts/quota-watchdog.sh {start [CONVERSATION_ID] [PROJECT_ID]|status|logs|drain [TIMEOUT]|stop [--force]|reset [CONVERSATION_ID] [PROJECT_ID]|once}" >&2
    exit 2
    ;;
esac
