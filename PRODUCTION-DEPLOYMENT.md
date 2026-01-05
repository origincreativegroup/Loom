# Loom OSINT Platform - Production Deployment Guide

## 🚨 Production Security Checklist

Before deploying Loom to production, ensure you complete ALL items in this checklist:

### Critical Security Requirements

- [ ] **Set Strong API Key**: Generate and set `OSINT_API_KEY` (use `openssl rand -base64 32`)
- [ ] **Change Database Passwords**: Update all default passwords in `.env`
- [ ] **Set ENVIRONMENT=production**: This enables critical security features
- [ ] **Configure ALLOWED_ORIGINS**: Restrict CORS to your actual domains only
- [ ] **Configure ALLOWED_HOSTS**: Set to your actual hostnames
- [ ] **Review SSH Keys**: Ensure SSH keys have proper permissions (600)
- [ ] **Configure known_hosts**: Set up SSH host key verification
- [ ] **Enable SSL/TLS**: Use reverse proxy (Caddy/nginx) with proper certificates
- [ ] **Review Firewall Rules**: Restrict access to necessary ports only
- [ ] **Set Up Monitoring**: Configure Prometheus/Grafana for metrics
- [ ] **Configure Logging**: Set up centralized log aggregation
- [ ] **Backup Strategy**: Implement regular backups of `/data` directory
- [ ] **Incident Response Plan**: Document security incident procedures

## Production Deployment Steps

### 1. Prerequisites

- Docker and Docker Compose installed
- Reverse proxy with SSL/TLS certificates (Caddy recommended)
- SSH access to target systems
- Database credentials secured
- Monitoring infrastructure ready

### 2. Environment Configuration

```bash
# Create production environment file
cp .env.example .env

# Generate strong API key
openssl rand -base64 32

# Edit .env with your production values
nano .env
```

**Required Environment Variables for Production:**

```bash
# CRITICAL: Set these values!
ENVIRONMENT=production
OSINT_API_KEY=<your-generated-api-key>

# CORS and Host Security
ALLOWED_ORIGINS=https://loom.yourdomain.com
ALLOWED_HOSTS=loom.yourdomain.com,loom.lan

# Database Credentials (CHANGE DEFAULTS!)
COUCHDB_PASS=<strong-password>
POSTGRES_PASS=<strong-password>

# Tool Integrations
SPIDERFOOT_API_KEY=<your-api-key>
INTELOWL_API_KEY=<your-api-key>
```

### 3. SSH Key Setup (for Recon-ng)

```bash
# Create keys directory
mkdir -p keys

# Generate SSH key pair
ssh-keygen -t ed25519 -f keys/id_ed25519 -N "" -C "loom-osint-production"

# Set proper permissions
chmod 600 keys/id_ed25519
chmod 644 keys/id_ed25519.pub

# Copy public key to remote host
ssh-copy-id -i keys/id_ed25519.pub admin@192.168.50.168

# Create known_hosts file for SSH host verification
ssh-keyscan -H 192.168.50.168 > keys/known_hosts
chmod 644 keys/known_hosts
```

### 4. Docker Images

```bash
# Pull required OSINT tool images
docker pull theharvester:latest
docker pull sherlock/sherlock:latest

# Verify images
docker images | grep -E 'theharvester|sherlock'
```

### 5. Production Deployment

```bash
# Deploy using production docker-compose
docker compose -f docker-compose.prod.yml up -d

# Verify containers are running
docker compose -f docker-compose.prod.yml ps

# Check logs
docker compose -f docker-compose.prod.yml logs -f

# Verify health checks
curl http://localhost:8787/health
curl http://localhost:8788/nginx-health
```

### 6. Reverse Proxy Configuration (Caddy)

Add to your Caddyfile on pi-net gateway:

```caddy
# Loom API
loom-api.lan {
    reverse_proxy <loom-host-ip>:8787

    # Rate limiting
    rate_limit {
        zone loom_api {
            key {remote_host}
            events 100
            window 1m
        }
    }
}

# Loom UI
loom.lan {
    reverse_proxy <loom-host-ip>:8788

    # Security headers (additional to app headers)
    header {
        -Server
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    }
}
```

Reload Caddy:
```bash
sudo systemctl reload caddy
```

### 7. Monitoring Setup

#### Prometheus Configuration

Add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'loom-osint'
    static_configs:
      - targets: ['<loom-host-ip>:8787']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

#### Grafana Dashboard

Import the Loom dashboard (create custom dashboard with metrics):

- `loom_http_requests_total` - Total HTTP requests by endpoint
- `loom_http_request_duration_seconds` - Request latency
- `loom_cases_created_total` - Cases created over time
- `loom_cases_completed_total` - Successful case completions
- `loom_cases_failed_total` - Failed cases
- `loom_tools_executed_total` - Tool execution statistics
- `loom_active_cases` - Currently active investigations

### 8. Log Aggregation

Configure centralized logging (example with Loki):

```yaml
# docker-compose.prod.yml - add logging driver
logging:
  driver: loki
  options:
    loki-url: "http://<loki-host>:3100/loki/api/v1/push"
    loki-batch-size: "400"
```

### 9. Backup Strategy

Create backup script:

```bash
#!/bin/bash
# /opt/loom/backup.sh

BACKUP_DIR="/backups/loom"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup data directory
tar -czf "${BACKUP_DIR}/loom-data-${DATE}.tar.gz" /path/to/loom/data

# Backup PostgreSQL
pg_dump -h <pg-host> -U postgres automation > "${BACKUP_DIR}/postgres-${DATE}.sql"

# Backup CouchDB
curl -X GET "https://<couch-user>:<couch-pass>@couchdb.lan/osint_scans/_all_docs?include_docs=true" \
  > "${BACKUP_DIR}/couchdb-${DATE}.json"

# Keep last 7 days
find "${BACKUP_DIR}" -type f -mtime +7 -delete
```

Add to crontab:
```bash
0 2 * * * /opt/loom/backup.sh
```

### 10. Health Monitoring

Create health check script:

```bash
#!/bin/bash
# /opt/loom/health-check.sh

API_URL="https://loom-api.lan"
UI_URL="https://loom.lan"
API_KEY="your-api-key"

# Check API health
API_STATUS=$(curl -s -H "X-API-Key: $API_KEY" "$API_URL/health" | jq -r '.api')

if [ "$API_STATUS" != "ok" ]; then
    echo "ALERT: Loom API unhealthy" | mail -s "Loom Health Alert" admin@example.com
fi

# Check UI
UI_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$UI_URL")

if [ "$UI_STATUS" != "200" ]; then
    echo "ALERT: Loom UI unreachable" | mail -s "Loom Health Alert" admin@example.com
fi
```

### 11. Security Hardening

#### Firewall Rules (iptables example)

```bash
# Allow only necessary ports
iptables -A INPUT -p tcp --dport 8787 -s <trusted-network> -j ACCEPT
iptables -A INPUT -p tcp --dport 8788 -s <trusted-network> -j ACCEPT
iptables -A INPUT -p tcp --dport 8787 -j DROP
iptables -A INPUT -p tcp --dport 8788 -j DROP
```

#### Docker Security

```bash
# Enable Docker Content Trust
export DOCKER_CONTENT_TRUST=1

# Scan images for vulnerabilities
docker scan theharvester:latest
docker scan sherlock/sherlock:latest
```

### 12. Performance Tuning

#### PostgreSQL Connection Pool

Adjust in `.env`:
```bash
# Increase pool size for high load
POSTGRES_MIN_POOL_SIZE=5
POSTGRES_MAX_POOL_SIZE=20
```

#### Uvicorn Workers

For production, use multiple workers:
```bash
# In docker-compose.prod.yml, already configured with:
--workers 4
```

### 13. Maintenance Tasks

#### Regular Updates

```bash
# Update Docker images monthly
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# Update Python dependencies
pip list --outdated
```

#### Log Rotation

Docker logs are automatically rotated (configured in docker-compose.prod.yml).

#### Database Maintenance

```bash
# PostgreSQL vacuum (monthly)
psql -h <pg-host> -U postgres -d automation -c "VACUUM ANALYZE;"

# CouchDB compaction (weekly)
curl -X POST "https://<user>:<pass>@couchdb.lan/osint_scans/_compact" \
  -H "Content-Type: application/json"
```

## Production Verification

After deployment, verify all systems:

1. **API Health**: `curl -H "X-API-Key: $API_KEY" https://loom-api.lan/health`
2. **Metrics**: Visit `https://loom-api.lan/metrics`
3. **UI Access**: Visit `https://loom.lan`
4. **Create Test Case**: Run a test OSINT investigation
5. **Check Logs**: `docker compose -f docker-compose.prod.yml logs -f`
6. **Verify Backups**: Ensure backup script runs successfully
7. **Test Alerts**: Trigger health check alerts

## Troubleshooting

### API Not Responding

```bash
# Check container status
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs loom-api

# Restart service
docker compose -f docker-compose.prod.yml restart loom-api
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
psql -h <pg-host> -U postgres -d automation -c "SELECT 1"

# Test CouchDB connection
curl -u admin:<pass> https://couchdb.lan/_up
```

### High Memory Usage

```bash
# Check container stats
docker stats

# Adjust resource limits in docker-compose.prod.yml
```

## Incident Response

### Security Breach Protocol

1. **Immediate Actions**:
   - Disconnect affected systems from network
   - Rotate all API keys and passwords
   - Review access logs: `docker compose logs | grep -i "403\|401"`
   - Check for unauthorized cases in `/data/cases`

2. **Investigation**:
   - Export logs for forensic analysis
   - Review Prometheus metrics for anomalies
   - Check PostgreSQL audit logs

3. **Recovery**:
   - Restore from last known good backup
   - Update security configurations
   - Patch vulnerabilities
   - Re-deploy with updated credentials

## Support and Maintenance

### Regular Security Reviews

- Monthly: Review access logs and failed authentication attempts
- Quarterly: Audit user permissions and API key usage
- Annually: Full security audit and penetration testing

### Documentation Updates

Keep this document updated with:
- Configuration changes
- New security requirements
- Lessons learned from incidents
- Performance tuning discoveries

## References

- [FastAPI Security Best Practices](https://fastapi.tiangolo.com/tutorial/security/)
- [Docker Security](https://docs.docker.com/engine/security/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)
