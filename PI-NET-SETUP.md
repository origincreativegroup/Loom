# Loom Deployment on Pi-Net - Quick Start Guide

This guide is specifically tailored for your pi-net infrastructure.

## Your Pi-Net Architecture

Your network has these key hosts:
- **pi-net (Gateway)**: 192.168.50.70 - Caddy, Pi-hole, WireGuard
- **NexusNAS**: 192.168.50.199 - Docker services, storage
- **Pi-5 (pi-core)**: 192.168.50.168 - Ollama (port 11435)
- **Pi-Forge**: 192.168.50.157 - Ollama (port 11434)
- **AI-Srv**: 192.168.50.247 - Ollama (port 11434), ComfyUI

## Recommended Deployment: NexusNAS

Deploy Loom on **NexusNAS (192.168.50.199)** since it's your central Docker host.

### Step 1: SSH to NexusNAS

```bash
ssh admin@192.168.50.199
```

### Step 2: Clone Loom Repository

```bash
cd ~
git clone <loom-repo-url> loom
cd loom
```

### Step 3: Configure for Pi-Net

```bash
cp .env.example .env
nano .env
```

Update the configuration:

```bash
# Use Pi-Forge Ollama (balanced load)
OLLAMA_URL=http://192.168.50.157:11434

# Or use Pi-5 Ollama
# OLLAMA_URL=http://192.168.50.168:11435

# Model (check what's installed: ssh to Pi-Forge and run 'ollama list')
OLLAMA_MODEL=llama3.2:latest

# SearXNG - you'll need to deploy this first (see below)
# For now, use a public instance:
SEARXNG_URL=https://search.bus-hit.me

# Optional API key for security
OSINT_API_KEY=
```

### Step 4: Deploy Loom

```bash
docker compose up -d
```

### Step 5: Verify Deployment

```bash
# Check containers are running
docker compose ps

# Check logs
docker compose logs -f

# Test API health
curl http://localhost:8787/health
```

Access Loom:
- **UI**: http://192.168.50.199:8788
- **API**: http://192.168.50.199:8787/docs

## Step 6: Setup Caddy Reverse Proxy (Recommended)

SSH to pi-net gateway:

```bash
ssh admin@192.168.50.70
```

Edit Caddy config:

```bash
sudo nano /etc/caddy/Caddyfile
```

Add these entries:

```caddy
loom.lan {
    reverse_proxy 192.168.50.199:8788
}

loom-api.lan {
    reverse_proxy 192.168.50.199:8787
}
```

Add DNS entries:

```bash
sudo nano /etc/dnsmasq.d/02-lan-hosts.conf
```

Add:

```
address=/loom.lan/192.168.50.70
address=/loom-api.lan/192.168.50.70
```

Restart services:

```bash
sudo systemctl reload caddy
sudo systemctl restart dnsmasq
```

Now access via:
- **UI**: https://loom.lan
- **API**: https://loom-api.lan/docs

## Step 7: Deploy SearXNG (Optional but Recommended)

For better OSINT results, deploy SearXNG on NexusNAS:

```bash
# On NexusNAS
mkdir -p ~/searxng
cd ~/searxng

# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    ports:
      - "8080:8080"
    volumes:
      - ./searxng:/etc/searxng
    environment:
      - SEARXNG_BASE_URL=https://search.lan/
    restart: unless-stopped
EOF

# Start SearXNG
docker compose up -d
```

Add to Caddy on pi-net:

```caddy
search.lan {
    reverse_proxy 192.168.50.199:8080
}
```

Update Loom's `.env`:

```bash
SEARXNG_URL=https://search.lan
```

Restart Loom:

```bash
cd ~/loom
docker compose restart
```

## Testing Your Deployment

### 1. Verify Ollama Access

From NexusNAS:

```bash
# Test Pi-Forge Ollama
curl http://192.168.50.157:11434/api/tags

# Test Pi-5 Ollama
curl http://192.168.50.168:11435/api/tags
```

### 2. Check Health Status

Visit https://loom.lan and check the status indicator at the top.

### 3. Run a Test Investigation

1. Go to https://loom.lan
2. Enter a test case:
   - **Title**: "Test Investigation"
   - **Initial Query**: "latest cybersecurity news"
3. Click "Run Pipeline"
4. Wait 30-60 seconds for results

## Integration with Existing Pi-Net Services

### n8n Automation (n8n.lan)

Trigger Loom investigations from n8n workflows:

```javascript
// HTTP Request node to Loom API
POST https://loom-api.lan/cases
Headers: {
  "Content-Type": "application/json",
  "X-API-Key": "your-api-key"
}
Body: {
  "title": "Automated Investigation",
  "initial_query": "{{$json.query}}"
}
```

### OpenWebUI Integration (ai.lan)

Use Loom reports in OpenWebUI RAG:
1. Loom saves reports to `/data/cases/<case_id>/report.md`
2. Mount this in OpenWebUI for document indexing

### Gitea Integration (git.lan)

Store investigation reports in Git:

```bash
# Create a cron job on NexusNAS
cat > ~/loom-backup.sh << 'EOF'
#!/bin/bash
cd ~/loom/data/cases
git add .
git commit -m "Auto-backup: $(date)"
git push
EOF

chmod +x ~/loom-backup.sh
crontab -e
# Add: 0 * * * * ~/loom-backup.sh
```

## Monitoring & Maintenance

### View Logs

```bash
cd ~/loom
docker compose logs -f
```

### Monitor Resource Usage

```bash
docker stats loom-api loom-ui
```

### Update Loom

```bash
cd ~/loom
git pull
docker compose up -d --build
```

### Backup Cases

```bash
# Backup to NAS
tar -czf ~/backups/loom-$(date +%Y%m%d).tar.gz ~/loom/data/

# Or use rsync to a network share
rsync -av ~/loom/data/ /mnt/nas/loom-backups/
```

## Portainer Management

Access Loom containers via Portainer:
1. Go to https://portainer.lan
2. Select NexusNAS endpoint
3. Find `loom-api` and `loom-ui` containers
4. View logs, stats, console

## WireGuard Remote Access

To access Loom remotely via WireGuard VPN:

1. Connect to WireGuard VPN (10.0.0.0/24)
2. Access https://loom.lan from anywhere
3. All pi-net services available securely

## Troubleshooting

### Issue: "Ollama API error"

```bash
# Test from NexusNAS
curl http://192.168.50.157:11434/api/tags

# If fails, SSH to Pi-Forge
ssh admin@192.168.50.157
docker ps | grep ollama
# Restart if needed
```

### Issue: "SearXNG unreachable"

```bash
# If using public instance, try another:
SEARXNG_URL=https://searx.be

# Or deploy your own (see Step 7)
```

### Issue: UI not loading

```bash
# Check Caddy on pi-net
ssh admin@192.168.50.70
sudo systemctl status caddy

# Check DNS
nslookup loom.lan 192.168.50.70

# Check containers on NexusNAS
docker compose ps
docker compose logs loom-ui
```

## Performance Notes

With your hardware:
- **Pi-Forge** Ollama: ~15-30 sec per query/synthesis
- **AI-Srv** Ollama: ~10-20 sec (if N100 or better)
- Expected total pipeline time: 1-3 minutes

For faster results:
- Use smaller models (phi3:latest)
- Reduce SearXNG result count
- Load balance across multiple Ollama instances

## Next Steps

1. Deploy SearXNG for private search
2. Add Caddy reverse proxy for https://loom.lan
3. Integrate with n8n for automated investigations
4. Set up case backup automation
5. Create custom investigation templates

## Support

Check service health:
- Loom UI: https://loom.lan
- Loom API: https://loom-api.lan/health
- Portainer: https://portainer.lan
- Ollama (Pi-Forge): http://192.168.50.157:11434/api/tags
