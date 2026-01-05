#!/bin/bash
# Deploys changes and restarts Docker containers on Pi-Forge

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="$SCRIPT_DIR/keys/id_ed25519_piforge"
REMOTE_HOST="admin@192.168.50.157"
REMOTE_DIR="~/loom-dev"

echo "🚀 Deploying to Pi-Forge..."

ssh -i "$KEY_FILE" "$REMOTE_HOST" << EOF
set -e
cd $REMOTE_DIR

if [ ! -f docker-compose.yml ]; then
    echo "❌ docker-compose.yml not found in $REMOTE_DIR"
    exit 1
fi

echo "🛑 Stopping containers..."
docker compose down || true

echo "🔨 Building images..."
docker compose build --no-cache

echo "🚀 Starting containers..."
docker compose up -d

echo "✅ Deployment complete"
echo ""
echo "📊 Container status:"
docker compose ps
EOF

echo ""
echo "✅ Deployment finished"
echo ""
echo "To view logs, run: ./dev-logs.sh"

