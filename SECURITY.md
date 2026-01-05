# Loom OSINT Platform - Security Guidelines

## Overview

This document outlines security considerations, best practices, and guidelines for deploying and operating the Loom OSINT Orchestration Platform in production environments.

## Security Model

### Threat Model

Loom is designed for **internal network deployments** (LAN/VPN environments) and assumes:

- **Trusted Network**: Deployment within a controlled network perimeter
- **Authorized Users**: All users have legitimate OSINT investigation needs
- **Physical Security**: Infrastructure is physically secured
- **Network Segmentation**: OSINT tools are isolated from critical systems

### Out of Scope

Loom is **NOT designed for**:
- Public internet exposure
- Multi-tenant SaaS deployments
- Untrusted user environments
- Processing of sensitive/classified data without additional controls

## Authentication & Authorization

### API Key Authentication

**Implementation**:
- All API endpoints require `X-API-Key` header when `OSINT_API_KEY` is set
- Frontend automatically includes API key in requests
- Rate limiting applied per remote IP address

**Best Practices**:

```bash
# Generate strong API key (32+ bytes)
openssl rand -base64 32

# Set in .env
OSINT_API_KEY=<generated-key>

# Rotate quarterly
0 0 1 */3 * /opt/loom/rotate-api-key.sh
```

**Limitations**:
- Single shared API key (no per-user authentication)
- No fine-grained access control
- No audit trail of individual user actions

**Recommendations for Production**:

For enhanced security, consider implementing:

1. **OAuth 2.0 / OIDC Integration**
   ```python
   # Example: Integrate with your SSO provider
   from fastapi_sso.sso.google import GoogleSSO
   ```

2. **JWT-based Authentication**
   ```python
   from fastapi.security import HTTPBearer
   from jose import jwt
   ```

3. **Multi-factor Authentication (MFA)**
   - Integrate with TOTP/U2F providers
   - Enforce MFA for administrative functions

## Input Validation

### Current Protections

1. **Target Validation**:
   - Format validation (domain, IP, email, username)
   - Length restrictions (max 255 characters)
   - Injection pattern detection

2. **Sanitization**:
   - Control character removal
   - Command injection pattern blocking
   - SQL injection prevention (via parameterized queries)

3. **Pydantic Models**:
   - Type validation
   - Constraint enforcement
   - Custom validators

### Validation Rules

```python
# Blocked patterns in user input
dangerous_patterns = [';', '&&', '||', '`', '$(', '${']

# Maximum lengths
MAX_TARGET_LENGTH = 255
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000

# Allowed tool names
allowed_tools = {
    'searxng', 'recon-ng', 'theharvester',
    'sherlock', 'spiderfoot', 'intelowl'
}
```

### Limitations

- Validation is **not** a complete defense against all injection attacks
- OSINT tools themselves may have vulnerabilities
- User input is passed to external tools (within validated parameters)

### Defense in Depth

1. **Network Isolation**: Run OSINT tools in isolated containers/networks
2. **Least Privilege**: Tools run with minimal required permissions
3. **Monitoring**: Log all tool executions and review for anomalies
4. **Resource Limits**: Docker container resource constraints prevent DoS

## Network Security

### CORS Configuration

**Development**:
```bash
ALLOWED_ORIGINS=http://localhost:8788,http://localhost:3000
```

**Production**:
```bash
ALLOWED_ORIGINS=https://loom.yourdomain.com,https://loom.lan
```

**Never use**:
```bash
# DANGEROUS - Do not use in production!
ALLOWED_ORIGINS=*
```

### Host Header Validation

Production deployments enforce trusted host headers:

```bash
ALLOWED_HOSTS=loom.yourdomain.com,loom.lan
```

This prevents host header injection attacks.

### SSL/TLS

**Requirements**:
- **Mandatory** for production deployments
- Use reverse proxy (Caddy/nginx) with valid certificates
- Enforce HSTS headers
- Minimum TLS 1.2, prefer TLS 1.3

**Configuration Example (Caddy)**:
```caddy
loom.lan {
    reverse_proxy localhost:8787

    # Force HTTPS
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

    # TLS configuration
    tls {
        protocols tls1.2 tls1.3
    }
}
```

## Data Security

### Data Classification

| Data Type | Classification | Retention | Encryption |
|-----------|---------------|-----------|------------|
| OSINT Results | Internal | 90 days | At Rest |
| Case Metadata | Internal | 1 year | At Rest |
| API Keys | Secret | N/A | Environment |
| SSH Keys | Secret | N/A | Filesystem |
| Logs | Internal | 30 days | At Rest |

### Encryption

**At Rest**:
- Use encrypted filesystems for `/data` directory
- Database encryption (PostgreSQL: `pgcrypto`, CouchDB: encryption at rest)
- Encrypt backups before storage

**In Transit**:
- TLS for all external communications
- SSH for remote tool execution
- VPN for multi-site deployments

### Data Retention

**Automatic Cleanup Script**:

```bash
#!/bin/bash
# /opt/loom/cleanup-old-cases.sh

DATA_DIR="/data/cases"
RETENTION_DAYS=90

find "$DATA_DIR" -type d -mtime +$RETENTION_DAYS -exec rm -rf {} +
```

Add to crontab:
```bash
0 3 * * 0 /opt/loom/cleanup-old-cases.sh
```

### Sensitive Data Handling

**Do NOT use Loom for**:
- Personal identifiable information (PII) requiring GDPR compliance
- Protected health information (PHI)
- Payment card data (PCI-DSS scope)
- Classified government data

**If you must handle sensitive data**:
1. Implement encryption for specific fields
2. Add data masking in UI/API responses
3. Implement audit logging with tamper protection
4. Consult legal/compliance teams

## Container Security

### Docker Security Best Practices

1. **Read-Only Containers** (where possible):
   ```yaml
   read_only: true
   tmpfs:
     - /tmp:size=100M,noexec,nosuid,nodev
   ```

2. **No New Privileges**:
   ```yaml
   security_opt:
     - no-new-privileges:true
   ```

3. **Resource Limits**:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '2.0'
         memory: 2048M
   ```

4. **Non-Root User** (recommended enhancement):
   ```dockerfile
   RUN useradd -m -u 1000 loom
   USER loom
   ```

### Docker Socket Security

**Current Configuration**:
- Docker socket mounted for TheHarvester/Sherlock
- **Risk**: Container escape potential

**Mitigation**:
- Read-only socket mount (`:ro`)
- Consider Docker-in-Docker or sidecar pattern
- Monitor Docker API calls

**Alternative (More Secure)**:
```yaml
# Use Docker API over TCP with TLS
environment:
  - DOCKER_HOST=tcp://docker-api:2376
  - DOCKER_TLS_VERIFY=1
```

## SSH Security

### Key Management

1. **Generate Dedicated Keys**:
   ```bash
   ssh-keygen -t ed25519 -f keys/id_ed25519 -N ""
   ```

2. **Proper Permissions**:
   ```bash
   chmod 700 keys/
   chmod 600 keys/id_ed25519
   chmod 644 keys/id_ed25519.pub
   ```

3. **Host Key Verification**:
   ```bash
   # Development: disabled for .lan domains
   # Production: MUST enable
   ssh-keyscan -H picore.lan > keys/known_hosts
   ```

4. **Key Rotation**:
   - Rotate SSH keys every 6-12 months
   - Immediately rotate if compromise suspected

### SSH Hardening

On remote OSINT tool hosts:

```bash
# /etc/ssh/sshd_config
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
AllowUsers loom-service
```

## Rate Limiting

### Configured Limits

| Endpoint | Limit | Rationale |
|----------|-------|-----------|
| `GET /` | 60/min | Health checks |
| `GET /health` | 60/min | Monitoring |
| `GET /tools` | 30/min | Tool discovery |
| `POST /cases` | 10/min | Prevent abuse |
| `POST /chat` | 20/min | AI resource protection |
| `GET /cases/*` | 60/min | Case retrieval |

### Customization

Adjust in `main.py`:

```python
@app.post("/cases")
@limiter.limit("10/minute")  # Adjust as needed
async def create_case(request: Request, case_create: CaseCreate):
    ...
```

### Bypass for Automation

For legitimate automation exceeding rate limits:

1. **Increase limits** for specific IPs:
   ```python
   @limiter.limit("100/minute", key_func=lambda: get_trusted_ip())
   ```

2. **Use separate API key** with higher limits

3. **Implement token bucket** for burst traffic

## Monitoring & Logging

### Security Monitoring

**Key Metrics to Monitor**:

1. **Authentication Failures**:
   ```promql
   rate(loom_http_requests_total{status="403"}[5m]) > 10
   ```

2. **Rate Limit Hits**:
   ```promql
   rate(loom_http_requests_total{status="429"}[5m]) > 5
   ```

3. **Error Rate Spike**:
   ```promql
   rate(loom_cases_failed_total[5m]) > 0.5
   ```

4. **Unusual Activity Patterns**:
   - After-hours case creation
   - Rapid sequential cases from same IP
   - Unusual tool combinations

### Log Analysis

**Security-Relevant Log Events**:

```json
{
  "level": "WARNING",
  "message": "Invalid API key",
  "client_ip": "192.168.1.100",
  "request_id": "abc123"
}
```

**SIEM Integration**:

Export logs to SIEM platform:
```bash
# Filebeat, Fluentd, or Logstash
docker compose logs -f | logstash -f /etc/logstash/loom.conf
```

### Audit Trail

**Recommended Additions**:

1. **Database Audit Log**:
   ```python
   async def log_audit_event(user, action, resource):
       await pg_pool.execute("""
           INSERT INTO audit_log (user_id, action, resource, timestamp)
           VALUES ($1, $2, $3, NOW())
       """, user, action, resource)
   ```

2. **Immutable Logs**:
   - Use write-once storage
   - Sign logs with HMAC
   - Forward to external log collector

## Incident Response

### Detection

**Indicators of Compromise**:
- Unexpected API key usage
- Cases with suspicious targets
- Tool execution failures
- Unusual network traffic patterns
- Container restarts
- File system modifications in `/data`

### Response Procedures

**Immediate Actions**:

1. **Isolate System**:
   ```bash
   docker compose down
   # or
   iptables -A INPUT -j DROP
   ```

2. **Preserve Evidence**:
   ```bash
   # Snapshot containers
   docker commit loom-api loom-api-incident-$(date +%Y%m%d)

   # Export logs
   docker compose logs > incident-logs-$(date +%Y%m%d).log

   # Copy data directory
   cp -r data/ data-backup-$(date +%Y%m%d)/
   ```

3. **Review Logs**:
   ```bash
   # Check for failed auth
   grep "403" incident-logs.log

   # Check for unusual targets
   jq '.target' data/cases/*/case.json
   ```

4. **Rotate Credentials**:
   ```bash
   # Generate new API key
   openssl rand -base64 32 > new_api_key.txt

   # Update .env
   sed -i "s/OSINT_API_KEY=.*/OSINT_API_KEY=$(cat new_api_key.txt)/" .env
   ```

### Post-Incident

1. **Root Cause Analysis**: Document what happened, how, and why
2. **Remediation**: Patch vulnerabilities, update configurations
3. **Lessons Learned**: Update procedures and documentation
4. **Penetration Testing**: Verify fixes prevent recurrence

## Compliance Considerations

### GDPR

If processing EU citizen data:
- Implement data subject access requests (DSAR)
- Add data deletion capabilities
- Document data processing activities
- Implement consent mechanisms

### SOC 2

For SOC 2 compliance:
- Enable comprehensive audit logging
- Implement access reviews
- Document security policies
- Conduct regular security assessments

### Industry-Specific

Consult compliance team for:
- HIPAA (healthcare)
- PCI-DSS (payment data)
- FISMA (federal systems)
- ISO 27001

## Security Hardening Checklist

### Pre-Deployment

- [ ] Generate strong API key (32+ bytes)
- [ ] Change all default passwords
- [ ] Configure ALLOWED_ORIGINS and ALLOWED_HOSTS
- [ ] Set ENVIRONMENT=production
- [ ] Enable SSL/TLS
- [ ] Configure SSH known_hosts
- [ ] Set proper file permissions
- [ ] Review and minimize exposed ports
- [ ] Enable Docker content trust
- [ ] Scan container images for vulnerabilities

### Post-Deployment

- [ ] Verify authentication works
- [ ] Test rate limiting
- [ ] Confirm security headers present
- [ ] Validate input sanitization
- [ ] Review logs for errors
- [ ] Set up monitoring alerts
- [ ] Configure automated backups
- [ ] Document incident response procedures
- [ ] Schedule security reviews
- [ ] Plan for credential rotation

### Ongoing

- [ ] Weekly: Review access logs
- [ ] Monthly: Update dependencies
- [ ] Quarterly: Rotate API keys
- [ ] Annually: Security audit
- [ ] As needed: Vulnerability patching

## Reporting Security Issues

**DO NOT** open public GitHub issues for security vulnerabilities.

**Instead**:
1. Email security contact (set up dedicated email)
2. Use PGP encryption if possible
3. Include detailed reproduction steps
4. Allow reasonable time for patching (90 days)

**Responsible Disclosure Policy**:
- We will acknowledge receipt within 48 hours
- We will provide status updates every 7 days
- We will credit researchers (unless anonymity requested)
- We will notify you before public disclosure

## Security Resources

### Tools

- **Dependency Scanning**: `pip-audit`, `safety`
- **Container Scanning**: `docker scan`, `trivy`
- **SAST**: `bandit`, `semgrep`
- **DAST**: `OWASP ZAP`, `nuclei`
- **Secrets Detection**: `trufflehog`, `gitleaks`

### Standards & Frameworks

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [SANS Critical Security Controls](https://www.sans.org/critical-security-controls/)

### Training

- OSINT ethics and legal considerations
- Secure coding practices (Python/FastAPI)
- Container security fundamentals
- Incident response procedures

## Conclusion

Security is a continuous process, not a one-time configuration. Regular reviews, updates, and vigilance are essential to maintaining a secure OSINT platform.

**Remember**: Loom aggregates and correlates potentially sensitive OSINT data. Treat it with appropriate security controls for your organization's risk appetite and regulatory requirements.
