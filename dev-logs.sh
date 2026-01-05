#!/bin/bash
# Stream logs from Pi-Forge Loom containers

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="$SCRIPT_DIR/keys/id_ed25519_piforge"
REMOTE_HOST="admin@192.168.50.157"
REMOTE_DIR="~/loom-dev"

SERVICE="${1:-loom-api}"

echo "📋 Streaming logs for: $SERVICE"
echo "Press Ctrl+C to exit"
echo ""

ssh -i "$KEY_FILE" "$REMOTE_HOST" "cd $REMOTE_DIR && docker compose logs -f $SERVICE"

