# Loom v2.0 - OSINT Orchestration Platform Setup Guide

This guide walks you through deploying Loom v2.0 on your pi-net with full OSINT tool integration.

## What's New in v2.0

Loom is now a **unified OSINT orchestration platform** that integrates with your existing local tools:

- ✅ **SearXNG** - Web search (already configured)
- ✅ **Recon-ng** - Reconnaissance framework (SSH to pi-core)
- ✅ **TheHarvester** - Email/subdomain harvesting (Docker)
- ✅ **Sherlock** - Username search (Docker)
- ✅ **SpiderFoot** - OSINT automation (API at spider.lan)
- ✅ **IntelOwl** - Threat intelligence (API at intelowl.lan)

**New Features:**
- Multi-tool selection in web UI
- Parallel tool execution
- Tool-by-tool result display
- Unified AI-powered synthesis
- CouchDB storage integration
- PostgreSQL activity logging

---

## Prerequisites Check

Before deploying, verify these services are running on your pi-net:

### Required Services
```bash
# SearXNG on pi-core
curl http://192.168.50.168:8888

# Ollama on Pi-Forge or AI-Srv
curl http://192.168.50.157:11434/api/tags

# Recon-ng on pi-core (check via SSH)
ssh admin@192.168.50.168 "recon-ng --version"
# Should return: 5.1.2
```

### Optional Services
```bash
# SpiderFoot
curl https://spider.lan

# IntelOwl
curl https://intelowl.lan

# CouchDB
curl -u admin:Swimfast01 https://couchdb.lan/osint_scans

# PostgreSQL (on pi-core)
# Check that the osint_logs table exists in the automation database
```

---

## Step 1: Setup SSH Keys for Recon-ng Access

Loom needs SSH access to pi-core to run Recon-ng. Set this up once:

### On NexusNAS (Loom host):

```bash
# Create keys directory in Loom
cd ~/loom  # or wherever you cloned Loom
mkdir -p keys

# Generate Ed25519 key for Loom
ssh-keygen -t ed25519 -f keys/id_ed25519 -N "" -C "loom@nexusnas"

# Copy public key to pi-core
ssh-copy-id -i keys/id_ed25519.pub admin@192.168.50.168

# Test authentication
ssh -i keys/id_ed25519 admin@192.168.50.168 "recon-ng --version"
# Should return: 5.1.2 without prompting for password
```

**Security Note:** The `keys/` directory is git-ignored and mounted read-only in the Docker container.

---

## Step 1b: Setup SSH Keys for Pi-Forge (Optional)

If you need SSH access to Pi-Forge for management or troubleshooting:

### On NexusNAS (Loom host):

```bash
# Generate Ed25519 key for Pi-Forge
ssh-keygen -t ed25519 -f keys/id_ed25519_piforge -N "" -C "loom-piforge@nexusnas"

# Copy public key to Pi-Forge
ssh-copy-id -i keys/id_ed25519_piforge.pub admin@192.168.50.157

# Test authentication
ssh -i keys/id_ed25519_piforge admin@192.168.50.157 "echo 'SSH connection successful!'"
```

**Or use the automated setup script:**

```bash
./setup-piforge-ssh.sh
```

This will guide you through the setup process and test the connection.

---

## Step 2: Pull Required Docker Images

TheHarvester and Sherlock run in Docker containers. Pull them on NexusNAS:

```bash
# TheHarvester (574MB)
docker pull theharvester:latest

# Sherlock (399MB)
docker pull sherlock/sherlock:latest

# Verify
docker images | grep -E "theharvester|sherlock"
```

---

## Step 3: Configure Environment

Copy and edit the environment file:

```bash
cd ~/loom
cp .env.example .env
nano .env
```

### Minimum Configuration

These settings are pre-configured for your pi-net:

```bash
# Ollama (default: Pi-Forge)
OLLAMA_URL=http://192.168.50.157:11434
OLLAMA_MODEL=llama3.2:latest

# SearXNG (pi-core)
SEARXNG_URL=http://192.168.50.168:8888

# SSH for Recon-ng (pi-core)
PICORE_SSH_HOST=192.168.50.168
PICORE_SSH_USER=admin
PICORE_SSH_KEY=/app/keys/id_ed25519

# SpiderFoot
SPIDERFOOT_URL=https://spider.lan
SPIDERFOOT_API_KEY=  # Optional: Add if you have one

# IntelOwl
INTELOWL_URL=https://intelowl.lan
INTELOWL_API_KEY=  # Required for IntelOwl integration

# CouchDB
COUCHDB_URL=https://couchdb.lan
COUCHDB_USER=admin
COUCHDB_PASS=Swimfast01
COUCHDB_DB=osint_scans

# PostgreSQL (pi-core automation database)
POSTGRES_HOST=192.168.50.168
POSTGRES_PORT=5433
POSTGRES_DB=automation
POSTGRES_USER=postgres
POSTGRES_PASS=  # Add if you have a password set
```

### Optional: API Keys

For enhanced functionality:

```bash
# Secure the Loom API (recommended for VPN access)
OSINT_API_KEY=your-secret-key-here

# SpiderFoot API key (if configured)
SPIDERFOOT_API_KEY=your-spiderfoot-key

# IntelOwl API key (required for IntelOwl)
INTELOWL_API_KEY=your-intelowl-token
```

---

## Step 4: Deploy Loom

```bash
cd ~/loom

# Start services
docker compose up -d

# Check logs
docker compose logs -f loom-api

# Wait for "Application startup complete"
# Ctrl+C to exit logs

# Verify containers
docker compose ps
# Both loom-api and loom-ui should be "Up"
```

---

## Step 5: Verify Deployment

### Check API Health

```bash
curl http://localhost:8787/health | jq
```

Expected output:
```json
{
  "api": "ok",
  "ollama": "ok",
  "postgres": "ok",
  "couchdb": "ok"
}
```

### Check Available Tools

```bash
curl http://localhost:8787/tools | jq
```

Should list all 6 OSINT tools with their status.

### Access Web UI

Open browser to:
- **Direct:** http://192.168.50.199:8788
- **API Docs:** http://192.168.50.199:8787/docs

You should see the Loom v2.0 interface with tool selection checkboxes.

---

## Step 6: Add Caddy Reverse Proxy (Recommended)

Make Loom accessible via https://loom.lan:

### On pi-net gateway (192.168.50.70):

```bash
# Add to Caddyfile
sudo tee -a /etc/caddy/Caddyfile << 'EOF'

loom.lan {
    reverse_proxy 192.168.50.199:8788
}

loom-api.lan {
    reverse_proxy 192.168.50.199:8787
}
EOF

# Add DNS entries
echo "address=/loom.lan/192.168.50.70" | sudo tee -a /etc/dnsmasq.d/02-lan-hosts.conf
echo "address=/loom-api.lan/192.168.50.70" | sudo tee -a /etc/dnsmasq.d/02-lan-hosts.conf

# Reload services
sudo systemctl reload caddy
sudo systemctl restart dnsmasq
```

Now access via:
- **UI:** https://loom.lan
- **API:** https://loom-api.lan/docs

---

## Step 7: Run Your First Investigation

### Via Web UI

1. Go to https://loom.lan
2. Fill in the form:
   - **Title:** Test Investigation
   - **Target:** example.com
   - **Tools:** Check SearXNG, Recon-ng, TheHarvester
3. Click "Run OSINT Pipeline"
4. Wait 1-3 minutes for results

### Via API

```bash
curl -X POST https://loom-api.lan/cases \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Investigation",
    "description": "Testing Loom v2.0",
    "target": "example.com",
    "tools": ["searxng", "recon-ng", "theharvester"]
  }' | jq
```

---

## Troubleshooting

### Issue: Recon-ng tool fails

**Error:** "Permission denied" or "Connection refused"

**Solution:**
```bash
# Test SSH connection manually
ssh -i ~/loom/keys/id_ed25519 admin@192.168.50.168 "recon-ng --version"

# If it asks for password, re-run ssh-copy-id:
ssh-copy-id -i ~/loom/keys/id_ed25519.pub admin@192.168.50.168

# Verify key is in authorized_keys on pi-core
ssh admin@192.168.50.168 "cat ~/.ssh/authorized_keys | grep loom"
```

### Issue: TheHarvester or Sherlock not working

**Error:** "No such image" or "Container not found"

**Solution:**
```bash
# Pull images on NexusNAS
docker pull theharvester:latest
docker pull sherlock/sherlock:latest

# Restart Loom API
docker compose restart loom-api
```

### Issue: SpiderFoot or IntelOwl tools fail

**Error:** "API unreachable" or "Connection refused"

**Solution:**
```bash
# Verify services are running
curl https://spider.lan
curl https://intelowl.lan

# If using API keys, verify they're set in .env
grep -E "SPIDERFOOT_API_KEY|INTELOWL_API_KEY" .env

# Restart after updating .env
docker compose restart loom-api
```

### Issue: CouchDB or PostgreSQL not logging

**Error:** Silent failure, no errors shown

**Solution:**
```bash
# Check CouchDB
curl -u admin:Swimfast01 https://couchdb.lan/osint_scans

# Check PostgreSQL
ssh admin@192.168.50.168 "docker exec shared-postgres psql -U postgres -d automation -c 'SELECT COUNT(*) FROM osint_logs;'"

# These are optional - Loom will work without them
# But they provide useful logging and storage
```

### Check Logs

```bash
cd ~/loom

# API logs
docker compose logs loom-api

# Follow logs in real-time
docker compose logs -f

# Last 100 lines
docker compose logs --tail=100 loom-api
```

---

## Tool Configuration Guide

### Recon-ng Modules

Default: `recon/domains-hosts/hackertarget` (subdomain enumeration)

To customize via API:
```json
{
  "tools": ["recon-ng"],
  "tool_options": {
    "recon-ng": {
      "module": "recon/domains-hosts/google_site_web"
    }
  }
}
```

### TheHarvester Sources

Default: `google,bing,duckduckgo`

To customize:
```json
{
  "tools": ["theharvester"],
  "tool_options": {
    "theharvester": {
      "sources": "google,bing,linkedin,twitter"
    }
  }
}
```

### SearXNG Result Count

Default: 15 results per query

To customize:
```json
{
  "tools": ["searxng"],
  "tool_options": {
    "searxng": {
      "num_results": 30
    }
  }
}
```

---

## Performance Tuning

### Expected Execution Times (on your hardware)

With Pi-Forge Ollama (llama3.2:latest):
- **SearXNG only:** 30-60 seconds
- **Recon-ng + SearXNG:** 1-2 minutes
- **All 6 tools:** 3-5 minutes

### Faster Execution

1. **Use AI-Srv Ollama** (if available):
   ```bash
   OLLAMA_URL=http://192.168.50.247:11434
   ```

2. **Use smaller model:**
   ```bash
   OLLAMA_MODEL=phi3:latest
   ```

3. **Limit tools to essentials:**
   - Start with SearXNG + Recon-ng
   - Add others as needed

---

## Integration with Other Services

### n8n Workflow

Trigger Loom from n8n:

```javascript
// HTTP Request node
POST https://loom-api.lan/cases
{
  "title": "{{ $json.target }} Investigation",
  "target": "{{ $json.target }}",
  "tools": ["searxng", "recon-ng", "theharvester"]
}
```

### OpenWebUI RAG

Index Loom reports in Qdrant:

```bash
# Loom saves reports to:
#   /path/to/loom/data/cases/<case_id>/report.md
#
# Mount this directory in OpenWebUI's document indexer
# Or create a cron job to copy to OpenWebUI's watched folder
```

### Gitea Backup

Version control your investigations:

```bash
# Create cron job
crontab -e

# Add:
0 */6 * * * cd ~/loom/data && git add . && git commit -m "Auto-backup $(date)" && git push
```

---

## Security Best Practices

1. **Enable API Key:**
   ```bash
   OSINT_API_KEY=$(openssl rand -hex 32)
   ```

2. **LAN/VPN Only:**
   - Never expose to public internet
   - Use WireGuard VPN for remote access

3. **Rotate SSH Keys:**
   ```bash
   # Regenerate every 90 days
   ssh-keygen -t ed25519 -f keys/id_ed25519_new -N ""
   ssh-copy-id -i keys/id_ed25519_new.pub admin@192.168.50.168
   mv keys/id_ed25519_new keys/id_ed25519
   docker compose restart
   ```

4. **Monitor Logs:**
   ```bash
   # Check PostgreSQL logs
   ssh admin@192.168.50.168 "docker exec shared-postgres psql -U postgres -d automation -c \
     'SELECT tool_name, COUNT(*) as runs, \
      SUM(CASE WHEN status=\\'error\\' THEN 1 ELSE 0 END) as errors \
      FROM osint_logs GROUP BY tool_name;'"
   ```

---

## Maintenance

### Update Loom

```bash
cd ~/loom
git pull
docker compose down
docker compose up -d --build
```

### Backup Case Data

```bash
# Backup all cases
tar -czf loom-backup-$(date +%Y%m%d).tar.gz data/

# Restore
tar -xzf loom-backup-YYYYMMDD.tar.gz
```

### Clean Old Cases

```bash
# Remove cases older than 30 days
find data/cases -type d -mtime +30 -exec rm -rf {} \;
```

### Monitor Resources

```bash
docker stats loom-api loom-ui
```

---

## Next Steps

1. ✅ Deploy Loom v2.0
2. ✅ Run test investigation
3. ⏭️ Configure API keys for SpiderFoot/IntelOwl
4. ⏭️ Set up automated backups
5. ⏭️ Integrate with n8n workflows
6. ⏭️ Index reports in OpenWebUI RAG

---

## Support

**Documentation:**
- README.md - Overview
- DEPLOYMENT.md - General deployment guide
- PI-NET-SETUP.md - Pi-net specific guide
- SETUP-V2.md - This file (v2.0 setup)

**Check Status:**
- UI: https://loom.lan
- API Health: https://loom-api.lan/health
- Tools Status: https://loom-api.lan/tools

**Logs:**
```bash
docker compose logs -f loom-api
```

---

**Version:** 2.0.0
**Last Updated:** 2026-01-05
**Status:** Production Ready
