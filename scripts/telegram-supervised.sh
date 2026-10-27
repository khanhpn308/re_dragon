#!/usr/bin/env bash
# Persist logs even if the tmux session and all its processes exit.
set -euo pipefail
[[ "$#" -ge 2 ]] || { echo "Usage: telegram-supervised.sh LOG CMD..." >&2; exit 2; }
LOG="$1"
shift
umask 077
mkdir -p "$(dirname "$LOG")"
touch "$LOG"
chmod 600 "$LOG"
printf '[%s] telegram starting; stderr/stdout persist after tmux exits\n' "$(date --iso-8601=seconds)" >>"$LOG"
exec "$@" >>"$LOG" 2>&1
