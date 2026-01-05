#!/bin/bash
# Setup SSH for Pi-Forge (192.168.50.157)
# This script helps set up SSH key authentication to pi-forge

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYS_DIR="$SCRIPT_DIR/keys"
PIFORGE_HOST="192.168.50.157"
PIFORGE_USER="admin"
KEY_FILE="$KEYS_DIR/id_ed25519_piforge"

echo "Setting up SSH for Pi-Forge..."
echo ""

# Check if key exists
if [ ! -f "$KEY_FILE" ]; then
    echo "Error: SSH key not found at $KEY_FILE"
    exit 1
fi

# Display public key
echo "Public key to install on pi-forge:"
echo "-----------------------------------"
cat "${KEY_FILE}.pub"
echo ""
echo "-----------------------------------"
echo ""

# Try to copy key
echo "Attempting to copy public key to pi-forge..."
echo "You may be prompted for the password for ${PIFORGE_USER}@${PIFORGE_HOST}"
echo ""

# Accept host key first
ssh-keyscan -H "$PIFORGE_HOST" >> ~/.ssh/known_hosts 2>/dev/null || true

# Copy the key
if ssh-copy-id -i "${KEY_FILE}.pub" "${PIFORGE_USER}@${PIFORGE_HOST}"; then
    echo ""
    echo "✅ SSH key successfully installed on pi-forge!"
    echo ""
    echo "Testing connection..."
    if ssh -i "$KEY_FILE" -o ConnectTimeout=5 "${PIFORGE_USER}@${PIFORGE_HOST}" "echo 'SSH connection successful!'"; then
        echo ""
        echo "✅ SSH setup complete! You can now connect without a password."
        echo ""
        echo "Test connection manually with:"
        echo "  ssh -i $KEY_FILE ${PIFORGE_USER}@${PIFORGE_HOST}"
    else
        echo ""
        echo "⚠️  Key installed but connection test failed. Please verify manually."
    fi
else
    echo ""
    echo "⚠️  Automatic key installation failed."
    echo ""
    echo "Manual installation instructions:"
    echo "1. SSH to pi-forge:"
    echo "   ssh ${PIFORGE_USER}@${PIFORGE_HOST}"
    echo ""
    echo "2. Add this public key to ~/.ssh/authorized_keys:"
    echo "   mkdir -p ~/.ssh"
    echo "   chmod 700 ~/.ssh"
    echo "   echo '$(cat ${KEY_FILE}.pub)' >> ~/.ssh/authorized_keys"
    echo "   chmod 600 ~/.ssh/authorized_keys"
    echo ""
    echo "3. Test connection:"
    echo "   ssh -i $KEY_FILE ${PIFORGE_USER}@${PIFORGE_HOST}"
fi

