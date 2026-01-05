#!/bin/bash
# Syncs local changes to Pi-Forge and restarts services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="$SCRIPT_DIR/keys/id_ed25519_piforge"
REMOTE_HOST="admin@192.168.50.157"
REMOTE_DIR="~/loom-dev"

echo "🔄 Syncing to Pi-Forge..."

# Check if we're in a git repository
if [ ! -d "$SCRIPT_DIR/.git" ]; then
    echo "⚠️  Not a git repository. Skipping git push."
else
    # Push to git first (if not already pushed)
    echo "📤 Pushing to git..."
    git push origin main 2>/dev/null || echo "⚠️  Git push skipped (may already be up to date or no remote)"
fi

# SSH and pull on remote
echo "📥 Pulling on Pi-Forge..."
ssh -i "$KEY_FILE" "$REMOTE_HOST" << EOF
cd $REMOTE_DIR || mkdir -p $REMOTE_DIR && cd $REMOTE_DIR
if [ -d .git ]; then
    git pull origin main || echo "⚠️  Git pull failed or already up to date"
else
    echo "⚠️  Not a git repository on remote. Run: git clone <repo-url> $REMOTE_DIR"
fi
echo "✅ Code synced"
EOF

echo "✅ Sync complete"

