#!/bin/bash
# Check status of Loom on Pi-Forge

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="$SCRIPT_DIR/keys/id_ed25519_piforge"
REMOTE_HOST="admin@192.168.50.157"
REMOTE_DIR="~/loom-dev"

echo "📊 Loom Status on Pi-Forge"
echo "=========================="
echo ""

ssh -i "$KEY_FILE" "$REMOTE_HOST" << EOF
cd $REMOTE_DIR

echo "🐳 Docker Containers:"
docker compose ps 2>/dev/null || echo "  No containers running"

echo ""
echo "💾 Disk Usage:"
df -h / | tail -1 | awk '{print "  Available: " \$4 " / Total: " \$2}'

echo ""
echo "🔌 Service Health:"
if docker compose ps | grep -q "Up"; then
    echo "  API Health:"
    curl -s http://localhost:8787/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "    API not responding"
else
    echo "  Services not running"
fi

echo ""
echo "📁 Git Status:"
if [ -d .git ]; then
    echo "  Branch: \$(git branch --show-current)"
    echo "  Last commit: \$(git log -1 --format='%h - %s (%ar)')"
    echo "  Status: \$(git status --short | wc -l) uncommitted changes"
else
    echo "  Not a git repository"
fi
EOF

echo ""
echo "✅ Status check complete"

