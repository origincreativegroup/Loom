# Loom - Deployment Guide for Pi-Net

This guide will help you deploy Loom on your Pi-Net infrastructure.

## Prerequisites

### Hardware
- Raspberry Pi (64-bit recommended) for running Loom
- Additional Pi or server running Ollama (e.g., `pi-forge`)
- Pi or server running SearXNG

### Software
- Docker and Docker Compose installed on the Loom host Pi
- Ollama running and accessible on your network
- SearXNG running and accessible on your network

## Network Architecture

Typical pi-net setup:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Loom Host     │────▶│   pi-forge      │     │   SearXNG       │
│  192.168.50.10  │     │  192.168.50.20  │     │  192.168.50.30  │
│                 │     │                 │     │                 │
│  UI:   :8788    │     │  Ollama: :11434 │     │  Search: :8080  │
│  API:  :8787    │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Step-by-Step Deployment

### 1. Clone and Navigate

```bash
git clone <your-loom-repo>
cd Loom
```

### 2. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your actual pi-net addresses:

```bash
nano .env
```

**Important:** Update these values for your network:

```bash
# Example for a typical pi-net setup
OLLAMA_URL=http://192.168.50.20:11434
SEARXNG_URL=http://192.168.50.30:8080
OLLAMA_MODEL=llama3.2:latest
```

### 3. Verify Network Connectivity

Before starting Loom, verify you can reach your services:

```bash
# Test Ollama
curl http://192.168.50.20:11434/api/tags

# Test SearXNG
curl http://192.168.50.30:8080
```

### 4. Start Loom

```bash
docker compose up -d
```

### 5. Verify Deployment

Check that containers are running:

```bash
docker compose ps
```

You should see:
- `loom-api` (running)
- `loom-ui` (running)

### 6. Access Loom

- **Web UI:** `http://<loom-host-ip>:8788`
- **API Docs:** `http://<loom-host-ip>:8787/docs`
- **Health Check:** `http://<loom-host-ip>:8787/health`

Example (if Loom is at 192.168.50.10):
- UI: `http://192.168.50.10:8788`
- API: `http://192.168.50.10:8787/docs`

## Post-Deployment Configuration

### Setting Up Ollama Models

On your Ollama host (e.g., pi-forge):

```bash
# Pull the model you want to use
ollama pull llama3.2:latest

# Or for a smaller, faster model
ollama pull phi3:latest

# List available models
ollama list
```

Update the `OLLAMA_MODEL` in your `.env` file to match.

### Optional: Reverse Proxy with Caddy

If you're running Caddy on your pi-net, you can set up friendly URLs:

```caddy
# Add to your Caddyfile
osint.lan {
    reverse_proxy 192.168.50.10:8788
}

osint-api.lan {
    reverse_proxy 192.168.50.10:8787
}
```

Then access via:
- UI: `http://osint.lan`
- API: `http://osint-api.lan/docs`

### Optional: Enable API Key Authentication

For additional security (recommended for VPN access):

1. Generate a random API key:
```bash
openssl rand -hex 32
```

2. Add to `.env`:
```bash
OSINT_API_KEY=your-generated-key-here
```

3. Restart Loom:
```bash
docker compose restart
```

The UI will prompt for the API key on first use.

## Troubleshooting

### Check Logs

```bash
# All logs
docker compose logs

# API logs only
docker compose logs loom-api

# UI logs only
docker compose logs loom-ui

# Follow logs in real-time
docker compose logs -f
```

### Common Issues

**Issue: "Ollama API error"**
- Verify Ollama is running: `curl http://<ollama-ip>:11434/api/tags`
- Check network connectivity between Loom and Ollama
- Verify `OLLAMA_URL` in `.env` is correct

**Issue: "SearXNG unreachable"**
- Verify SearXNG is running: `curl http://<searxng-ip>:8080`
- Check network connectivity
- Verify `SEARXNG_URL` in `.env` is correct

**Issue: "Permission denied" for data directory**
- Ensure `./data` directory exists and is writable:
```bash
mkdir -p data/cases
chmod 755 data
```

**Issue: UI shows "API unreachable"**
- Check that the API container is running: `docker compose ps`
- Verify API health: `curl http://localhost:8787/health`
- Check browser console for CORS errors

### Restart Services

```bash
# Restart all services
docker compose restart

# Rebuild and restart (after code changes)
docker compose up -d --build

# Stop all services
docker compose down

# Stop and remove all data (WARNING: deletes cases!)
docker compose down -v
```

## Maintenance

### Updating Loom

```bash
git pull
docker compose up -d --build
```

### Backup Case Data

```bash
# Backup all cases
tar -czf loom-backup-$(date +%Y%m%d).tar.gz data/

# Restore from backup
tar -xzf loom-backup-YYYYMMDD.tar.gz
```

### Monitor Resource Usage

```bash
# Check container resource usage
docker stats loom-api loom-ui
```

## Security Best Practices

1. **LAN/VPN Only:** Loom is designed for local network use. Don't expose to the public internet.

2. **Use API Keys:** Enable `OSINT_API_KEY` for additional security.

3. **Reverse Proxy:** Use Caddy or Nginx with SSL for encrypted connections.

4. **WireGuard:** For remote access, use WireGuard VPN to your pi-net.

5. **Regular Updates:** Keep Docker, Ollama, and SearXNG updated.

## Performance Tuning

### For Raspberry Pi 4 (4GB+)
- Use `llama3.2:latest` or `phi3:latest` models
- Expect 10-30 seconds per query plan/synthesis

### For Raspberry Pi 5 or Server
- Can use larger models like `mixtral:latest`
- Faster response times (5-15 seconds)

### Optimize SearXNG
- Configure SearXNG to use faster engines
- Limit the number of engines for quicker results

## Next Steps

Once deployed:
1. Create a test case to verify the pipeline
2. Monitor logs for any errors
3. Adjust Ollama model based on performance
4. Configure SearXNG search engines for your use case
5. Set up Caddy reverse proxy for friendly URLs

## Support

For issues or questions:
- Check logs: `docker compose logs`
- Review health status: `http://<host>:8787/health`
- Verify network connectivity between all components
