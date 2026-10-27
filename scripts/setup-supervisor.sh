#!/usr/bin/env bash
# setup-supervisor.sh — RE Dragon Process Supervision Setup Assistant
# Does not mutate system configuration without explicit user action.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_FILE="$ROOT/services/re-dragon.service"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
TARGET_SERVICE="$USER_SYSTEMD_DIR/re-dragon.service"

echo "=== RE Dragon v0.8 Process Supervisor Configuration ==="
echo "Workspace: $ROOT"
echo "Service template: $SERVICE_FILE"

ACTION="${1:-help}"

case "$ACTION" in
  check)
    echo "1. Checking python and re_harness module..."
    python3 -m re_harness.supervisor status --workspace "$ROOT"
    echo "2. Checking systemd user availability..."
    if command -v systemctl >/dev/null 2>&1; then
      echo "systemctl is installed."
    else
      echo "systemctl is not installed or not in PATH."
    fi
    ;;

  status)
    python3 -m re_harness.supervisor status --workspace "$ROOT"
    ;;

  generate)
    python3 -m re_harness.supervisor generate-config --workspace "$ROOT"
    ;;

  install-systemd-user)
    echo "This will install the service to your user systemd directory: $TARGET_SERVICE"
    echo "It does not modify root/system-wide systemd or Windows settings."
    read -p "Proceed? (y/N): " -r CONFIRM
    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
      mkdir -p "$USER_SYSTEMD_DIR"
      cp "$SERVICE_FILE" "$TARGET_SERVICE"
      systemctl --user daemon-reload
      systemctl --user enable re-dragon.service
      echo "Installed and enabled user service. To start: systemctl --user start re-dragon.service"
    else
      echo "Aborted."
    fi
    ;;

  help|*)
    echo "Usage: ./scripts/setup-supervisor.sh {check|status|generate|install-systemd-user}"
    ;;
esac
