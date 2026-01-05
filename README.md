# Loom v2.0 — OSINT Orchestration Platform

Loom is a **unified web interface** for orchestrating local OSINT tools on your pi-net. Replace complex n8n workflows with a single, easy-to-use dashboard.

## Unified Tool Orchestration

**Intake → Multi-Tool Execution → AI Synthesis → Unified Report**

### Integrated Tools

- ✅ **SearXNG** - Private web search
- ✅ **Recon-ng** - Reconnaissance framework (subdomains, hosts)
- ✅ **TheHarvester** - Email & subdomain harvesting
- ✅ **Sherlock** - Username search across social media
- ✅ **SpiderFoot** - Automated OSINT collection
- ✅ **IntelOwl** - Threat intelligence analysis

### Core Features

- **🎯 Target-Based:** Single target, multiple tools
- **🤖 AI-Powered:** Ollama synthesizes results from all tools
- **📊 Rich UI:** Tool selection, progress tracking, per-tool results
- **💾 Persistent:** CouchDB storage + PostgreSQL logging
- **🔗 API-First:** Full REST API for automation

## Quick Start

**Full setup guide:** See [SETUP-V2.md](SETUP-V2.md) for complete deployment instructions.

### 1) Prerequisites

- Docker + Docker Compose
- SSH access to pi-core (for Recon-ng)
- Access to:
  - Ollama (Pi-Forge, AI-Srv, or pi-core)
  - SearXNG (pi-core:8888)
  - Optional: SpiderFoot, IntelOwl

### 2) Setup SSH Keys

```bash
cd /path/to/loom
mkdir -p keys
ssh-keygen -t ed25519 -f keys/id_ed25519 -N ""
ssh-copy-id -i keys/id_ed25519.pub admin@192.168.50.168
```

### 3) Pull Docker Images

```bash
docker pull theharvester:latest
docker pull sherlock/sherlock:latest
```

### 4) Configure & Deploy

```bash
cp .env.example .env
# Edit .env if needed (defaults work for pi-net)
docker compose up -d
```

### 5) Access

- **UI:** `http://<pi-ip>:8788`
- **API:** `http://<pi-ip>:8787/docs`
- **With Caddy:** `https://loom.lan`

## How It Works

### 1. Create Investigation
- Enter target (domain, IP, username, email)
- Select tools to run (SearXNG, Recon-ng, TheHarvester, etc.)
- Optionally configure per-tool options

### 2. Parallel Execution
- All selected tools run simultaneously
- Real-time progress tracking in UI
- Each tool returns structured results

### 3. AI Synthesis
- Ollama analyzes results from ALL tools
- Cross-references findings
- Generates unified intelligence report

### 4. Storage & Export
Saves to filesystem, CouchDB, and PostgreSQL:
```
/data/cases/<case_id>/
  ├── case.json          # Case metadata
  ├── report.md          # Unified AI-generated report
  └── tools/
      ├── searxng.json   # SearXNG results
      ├── recon-ng.json  # Recon-ng results
      └── ...            # Other tool results
```

## Security
- This is meant for LAN/VPN use.
- You can enable an API key by setting `OSINT_API_KEY` in `.env`.
  The UI will send `X-API-Key` automatically.

## Reverse proxy (optional)
If you run Caddy on `pi-net`, proxy the UI:

```caddy
osint.lan {
  reverse_proxy 192.168.50.X:8788
}
```

## Repo layout
```text
loom-mvp/
  docker-compose.yml
  .env.example
  app/
    main.py
    requirements.txt
  ui/
    index.html
    app.js
    style.css
  data/
    cases/   (created at runtime)
```

## Documentation

- **[README.md](README.md)** - This file (overview)
- **[SETUP-V2.md](SETUP-V2.md)** - Complete v2.0 setup guide
- **[PI-NET-SETUP.md](PI-NET-SETUP.md)** - Pi-net specific deployment
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - General deployment guide
- **[.env.example](.env.example)** - Configuration template

## Architecture

```
┌─────────────────────────────────────────────────┐
│          Loom Web UI (Port 8788)                │
│     Tool Selection │ Progress │ Results         │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│      Loom API (FastAPI - Port 8787)             │
│   Orchestration │ AI Synthesis │ Storage        │
└──┬────┬────┬────┬────┬────┬────────┬───────┬───┘
   │    │    │    │    │    │        │       │
   ▼    ▼    ▼    ▼    ▼    ▼        ▼       ▼
SearXNG │ Harvest│Sherlock│Spider  Intel  Couch Postgres
       Recon-ng  TheH.          Foot   Owl   DB   (logs)
```

## API Examples

### Create Investigation

```bash
curl -X POST http://localhost:8787/cases \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Company OSINT",
    "target": "example.com",
    "tools": ["searxng", "recon-ng", "theharvester"]
  }'
```

### List Cases

```bash
curl http://localhost:8787/cases | jq
```

### Get Tool Results

```bash
curl http://localhost:8787/cases/<case_id>/tools/recon-ng | jq
```

## What's New in v2.0

### ✅ Implemented
- Multi-tool orchestration (6 tools integrated)
- Tool selection UI with checkboxes
- Parallel tool execution
- Per-tool result display
- CouchDB storage integration
- PostgreSQL activity logging
- Unified AI synthesis across all tools
- SSH integration for Recon-ng
- Docker integration for TheHarvester/Sherlock
- API integration for SpiderFoot/IntelOwl

### 🚀 Future Enhancements
- Real-time WebSocket progress updates
- Case comparison and diff ing
- Custom tool plugins
- Scheduled/recurring investigations
- Alert system for new findings
- Export to PDF/JSON/CSV
- Integration with Maltego
- Qdrant vector storage for RAG
