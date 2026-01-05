# Loom - Simple Local Deployment Guide

## Quick Setup for Local/LAN Use

Loom is designed for **local network use** (your pi-net). The security features are there, but you don't need to go overboard.

### 5-Minute Setup

```bash
# 1. Copy environment file
cp .env.example .env

# 2. (Optional) Set an API key - or leave blank for local-only use
# OSINT_API_KEY=   # Leave empty for no auth

# 3. Setup SSH keys for Recon-ng
mkdir -p keys
ssh-keygen -t ed25519 -f keys/id_ed25519 -N ""
ssh-copy-id -i keys/id_ed25519.pub admin@192.168.50.168

# 4. Deploy
docker compose up -d

# 5. Access
# UI: http://<your-pi-ip>:8788
# API: http://<your-pi-ip>:8787/docs
```

That's it!

### What Actually Matters for Local Use

**DO configure**:
- SSH keys (for Recon-ng to work)
- Database credentials if you changed them
- Tool API keys (SpiderFoot, IntelOwl) if you're using them

**DON'T worry about**:
- API key authentication (leave `OSINT_API_KEY` empty for local-only)
- `ENVIRONMENT=production` (stay on development)
- `ALLOWED_ORIGINS` (default is fine for LAN)
- SSL certificates (your .lan domains work fine)

### Recommended .env for Local Use

```bash
# Just use the defaults in .env.example
# The only things you might change:

# If you want simple auth (optional):
OSINT_API_KEY=mysecretkey

# Database passwords (if you changed them):
COUCHDB_PASS=your-password
POSTGRES_PASS=your-password

# That's it!
```

### Using the Regular docker-compose.yml

The original `docker-compose.yml` is perfect for local use:

```bash
docker compose up -d
```

No need for `docker-compose.prod.yml` unless you want the extra features (multi-worker, resource limits, etc.).

### What You Get Automatically

Even without "production mode", you still get:
- ✅ Rate limiting (prevents accidental abuse)
- ✅ Input validation (prevents bad data)
- ✅ Security headers (doesn't hurt)
- ✅ Metrics endpoint at `/metrics` (if you want to monitor)
- ✅ Better logging (structured JSON)

These features work in development mode and don't require any extra config.

### When to Use "Production" Features

Only use `docker-compose.prod.yml` and `ENVIRONMENT=production` if:
- You're exposing Loom outside your local network
- You want strict SSL verification
- You need multi-worker performance
- You want enforced security policies

For normal pi-net use? **Skip all that!**

### Troubleshooting

**403 Forbidden errors?**
```bash
# Just remove the API key requirement
OSINT_API_KEY=   # Leave blank in .env
```

**CORS errors?**
```bash
# Shouldn't happen on LAN, but if it does:
ALLOWED_ORIGINS=http://192.168.50.199:8788,http://localhost:8788
```

**Rate limiting too strict?**
- It's pretty generous (10-60 req/min)
- You shouldn't hit it in normal use
- If you do, let me know and we can adjust

### Documentation Hierarchy

**For local/LAN use:**
1. This file (SIMPLE-SETUP.md) ← **Start here**
2. README.md - Overview and features
3. SETUP-V2.md - Detailed tool configuration

**For actual production (external exposure):**
1. PRODUCTION-DEPLOYMENT.md
2. SECURITY.md

### Summary

The codebase now has enterprise-grade features **available**, but you don't have to use them. Just:

1. Copy `.env.example` to `.env`
2. Setup SSH keys
3. Run `docker compose up -d`
4. Use it!

The security and monitoring features work quietly in the background without requiring configuration.
