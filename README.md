# Loom (MVP) — local-first OSINT console (GUI + API) powered by Ollama

Loom is a lightweight, self-hosted **web GUI** + **API** that replicates the “n8n workflow effect”:

**Intake → Plan → Tool Runs → Synthesis → Report Bundle**

- **Brain:** Ollama (remote, e.g. `pi-forge`)
- **Search tool:** SearXNG (`searxng.lan`) via JSON API
- **Storage:** Writes case folders to a mounted volume (`./data` → `/data`)
- **UI:** simple web dashboard (static HTML) served by Nginx

## Quick start

### 1) Prereqs
- Docker + docker compose on a Pi (64-bit strongly preferred)
- Reachability to:
  - Ollama: `http://pi-forge.nexus.lan:11434` (or your endpoint)
  - SearXNG: `https://searxng.lan`

### 2) Configure
Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
```

### 3) Run
```bash
docker compose up -d
```

- UI: `http://<pi-ip>:8788`
- API: `http://<pi-ip>:8787/docs`

## What “Run pipeline” does
1. Creates (or uses) a case
2. Asks Ollama to generate a **query plan** (structured JSON)
3. Executes SearXNG searches for those queries
4. Asks Ollama to synthesize results into a **structured JSON report**
5. Writes:
   - `/data/cases/<case_id>/case.json`
   - `/data/cases/<case_id>/raw/searx_bundle_*.json`
   - `/data/cases/<case_id>/report.md`

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

## Notes / roadmap
- Add tool registry + dynamic `tool_plan[]` execution (Sherlock/SpiderFoot/etc.)
- Add case list UI + re-runs + diffing
- Add auth (basic auth behind Caddy) or WireGuard-only access
- Add connectors to your local stores later (NAS notes, PDFs, etc.)
