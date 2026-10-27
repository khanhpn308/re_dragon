#!/usr/bin/env bash
# setup-supervisor.sh — RE Dragon Process Supervision Setup Assistant
# Does not mutate system configuration without explicit user action.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_WS="${2:-$ROOT}"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
TARGET_SERVICE="$USER_SYSTEMD_DIR/re-dragon.service"

echo "=== RE Dragon v0.8 Process Supervisor Configuration ==="
echo "Target Workspace: $TARGET_WS"

ACTION="${1:-help}"

case "$ACTION" in
  check)
    echo "1. Checking supervisor status for workspace..."
    python3 -m re_harness.supervisor status --workspace "$TARGET_WS"
    echo "2. Checking systemd user availability..."
    if command -v systemctl >/dev/null 2>&1; then
      echo "systemctl is installed."
    else
      echo "systemctl is not installed or not in PATH."
    fi
    ;;

  status)
    python3 -m re_harness.supervisor status --workspace "$TARGET_WS"
    ;;

  generate)
    python3 -m re_harness.supervisor generate-config --workspace "$TARGET_WS"
    ;;

  install-systemd-user)
    echo "Verifying target workspace binding before installation..."
    python3 -c "from re_harness.supervisor import verify_workspace_binding; print('Verified:', verify_workspace_binding('$TARGET_WS'))"
    echo "This will install the generated service to your user systemd directory: $TARGET_SERVICE"
    echo "It does not modify root/system-wide systemd or Windows settings."
    read -p "Proceed? (y/N): " -r CONFIRM
    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
      mkdir -p "$USER_SYSTEMD_DIR"
      python3 -c "from re_harness.supervisor import generate_systemd_unit; print(generate_systemd_unit('$TARGET_WS'))" > "$TARGET_SERVICE"
      systemctl --user daemon-reload
      systemctl --user enable re-dragon.service
      echo "Installed and enabled user service for $TARGET_WS. To start: systemctl --user start re-dragon.service"
    else
      echo "Aborted."
    fi
    ;;

  help|*)
    echo "Usage: ./scripts/setup-supervisor.sh {check|status|generate|install-systemd-user} [WORKSPACE_PATH]"
    ;;
esac
