# 👋 Start Here

## New to Loom? Read This First

Loom is an **OSINT (Open Source Intelligence) orchestration platform** for your local network.

### What It Does

- Run multiple OSINT tools against a target (domain, IP, username, email)
- Aggregate results from tools like SearXNG, Recon-ng, TheHarvester, Sherlock, etc.
- Use AI (Ollama) to synthesize findings into a unified report
- Store investigations in CouchDB and PostgreSQL

### Quick Start (5 Minutes)

**For simple local/LAN deployment** (recommended):
→ See [SIMPLE-SETUP.md](SIMPLE-SETUP.md)

**For detailed setup with all features**:
→ See [SETUP-V2.md](SETUP-V2.md)

**For production deployment outside your network**:
→ See [PRODUCTION-DEPLOYMENT.md](PRODUCTION-DEPLOYMENT.md) (probably overkill)

### Documentation Map

```
START-HERE.md (this file)
├─ SIMPLE-SETUP.md ⭐ Most users start here
├─ README.md - Features and overview
├─ SETUP-V2.md - Detailed setup guide
│
└─ Advanced (optional):
   ├─ PRODUCTION-DEPLOYMENT.md - Enterprise deployment
   ├─ SECURITY.md - Security hardening guide
   └─ PRODUCTION-READINESS-SUMMARY.md - Change summary
```

### The Simple Version

```bash
# 1. Copy config
cp .env.example .env

# 2. Setup SSH (for Recon-ng)
mkdir -p keys
ssh-keygen -t ed25519 -f keys/id_ed25519 -N ""
ssh-copy-id -i keys/id_ed25519.pub admin@192.168.50.168

# 3. Start it
docker compose up -d

# 4. Open browser
# http://<your-pi-ip>:8788
```

### Common Questions

**Q: Do I need to set up API keys and security stuff?**
A: Not for local LAN use. It's all optional.

**Q: Should I use docker-compose.prod.yml?**
A: Only if you're exposing this outside your network. Use regular `docker-compose.yml` for local.

**Q: What about the ENVIRONMENT variable?**
A: Leave it as `development` for local use. This keeps SSL verification off for .lan domains.

**Q: Do I need to configure ALLOWED_ORIGINS?**
A: Nope, defaults work fine for LAN deployment.

**Q: Should I read all the security documentation?**
A: Only if you're exposing Loom outside your local network. For LAN use, the defaults are secure enough.

### Need Help?

1. Check [SIMPLE-SETUP.md](SIMPLE-SETUP.md)
2. Review logs: `docker compose logs -f`
3. Check health: `curl http://localhost:8787/health`
4. Look at specific error in logs

### What's New in Latest Version

- Better security (but optional for local use)
- Rate limiting (prevents accidental API spam)
- Prometheus metrics at `/metrics`
- Better logging
- All the good stuff works automatically, no config needed!

---

**TL;DR**: Copy `.env.example` to `.env`, setup SSH keys, run `docker compose up -d`. Done!
