#!/bin/bash
# Open interactive shell on Pi-Forge in Loom directory

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="$SCRIPT_DIR/keys/id_ed25519_piforge"
REMOTE_HOST="admin@192.168.50.157"
REMOTE_DIR="~/loom-dev"

echo "🐚 Opening shell on Pi-Forge..."
echo "Working directory: $REMOTE_DIR"
echo ""

ssh -i "$KEY_FILE" -t "$REMOTE_HOST" "cd $REMOTE_DIR && exec \$SHELL"

