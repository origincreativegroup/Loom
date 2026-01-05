# Loom Odoo Integration

This document describes the Odoo ERP/CRM integration for Loom, enabling bi-directional intelligence between OSINT investigations and business operations.

## Overview

Loom integrates with Odoo 17 to:
- **READ**: Search and retrieve business context (contacts, leads, projects, tasks, activities, calendar)
- **WRITE (GATED)**: Propose and execute business actions with explicit confirmation

## Architecture

```
┌─────────────────────────────────────────────┐
│         Loom API (FastAPI)                  │
│  ┌─────────────────────────────────────┐   │
│  │     Odoo Client (XML-RPC)           │   │
│  │  - OdooClient (auth & connection)   │   │
│  │  - OdooReadOperations (safe reads)  │   │
│  │  - OdooWriteOperations (gated)      │   │
│  └─────────────────────────────────────┘   │
└──────────────────┬──────────────────────────┘
                   │ XML-RPC Protocol
┌──────────────────▼──────────────────────────┐
│      Odoo 17 (https://ocg.lan)              │
│  - res.partner (Contacts/Companies)         │
│  - crm.lead (Opportunities)                 │
│  - project.project (Projects)               │
│  - project.task (Tasks)                     │
│  - mail.activity (Planned Actions)          │
│  - calendar.event (Meetings/Events)         │
└─────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Odoo Connection
ODOO_URL=https://ocg.lan
ODOO_DB=ocg_production
ODOO_USERNAME=loom@ocg.lan
ODOO_PASSWORD=your_secure_password

# Optional Settings
ODOO_SEARCH_FIELDS=email,phone,name,website
ODOO_INCLUDE_CUSTOMERS=true
ODOO_INCLUDE_OPPORTUNITIES=true
```

### Odoo User Setup

**IMPORTANT**: Create a dedicated Loom user in Odoo with limited permissions:

1. Go to Odoo Settings → Users & Companies → Users
2. Create new user: `loom@ocg.lan`
3. Assign access rights:
   - **Contacts**: Read/Write
   - **CRM**: Read/Write
   - **Project**: Read/Write
   - **Calendar**: Read/Write
4. Enable API Access
5. Set strong password

## API Endpoints

### Status & Health

#### `GET /odoo/status`
Check Odoo connection status and version.

**Response:**
```json
{
  "connected": true,
  "odoo_version": "17.0",
  "database": "ocg_production",
  "username": "loom@ocg.lan"
}
```

---

### READ Operations (Safe - No Confirmation Required)

All READ operations are safe and can be executed without confirmation.

#### `POST /odoo/search/partners`
Search for contacts/companies.

**Payload:**
```json
{
  "query": "John Doe",
  "email": "john@example.com",
  "phone": "+1234567890",
  "website": "example.com",
  "is_company": true,
  "limit": 100
}
```

**Response:**
```json
{
  "count": 5,
  "partners": [
    {
      "id": 123,
      "name": "Example Corp",
      "email": "contact@example.com",
      "phone": "+1234567890",
      "website": "https://example.com",
      "is_company": true,
      "city": "San Francisco",
      "country_id": [233, "United States"]
    }
  ]
}
```

#### `GET /odoo/partners/{partner_id}`
Get full history for a partner (leads, projects, tasks, activities, events).

**Response:**
```json
{
  "partner": { /* partner details */ },
  "leads": [ /* related opportunities */ ],
  "projects": [ /* related projects */ ],
  "tasks": [ /* related tasks */ ],
  "activities": [ /* scheduled activities */ ],
  "calendar_events": [ /* meetings/events */ ]
}
```

#### `POST /odoo/search/leads`
Search CRM opportunities.

**Payload:**
```json
{
  "partner_id": 123,
  "email": "john@example.com",
  "name": "Web Design Project",
  "stage": "Qualification",
  "limit": 100
}
```

#### `POST /odoo/search/projects`
Search projects.

**Payload:**
```json
{
  "partner_id": 123,
  "name": "Website Redesign",
  "limit": 100
}
```

#### `POST /odoo/search/tasks`
Search project tasks.

**Payload:**
```json
{
  "project_id": 45,
  "partner_id": 123,
  "name": "Design mockups",
  "limit": 100
}
```

#### `POST /odoo/search/activities`
Search scheduled activities.

**Payload:**
```json
{
  "partner_id": 123,
  "res_model": "crm.lead",
  "res_id": 67,
  "limit": 100
}
```

#### `POST /odoo/search/calendar`
Search calendar events.

**Payload:**
```json
{
  "partner_ids": [123, 456],
  "name": "Project Kickoff",
  "limit": 100
}
```

---

### WRITE Operations (GATED - Require Confirmation)

All WRITE operations follow a **propose → confirm → execute** workflow.

#### Step 1: Propose

**Propose Creating/Updating a Partner:**

```bash
POST /odoo/propose/partner
```

**Payload:**
```json
{
  "name": "Example Corp",
  "email": "contact@example.com",
  "phone": "+1234567890",
  "website": "https://example.com",
  "is_company": true,
  "street": "123 Main St",
  "city": "San Francisco",
  "country_code": "US",
  "comment": "OSINT investigation target",
  "case_id": "abc12345"
}
```

**Response (Proposal):**
```json
{
  "proposal_id": "f8a3b21c",
  "summary": "Create partner: Example Corp (contact@example.com)",
  "operations": [
    {
      "op": "upsert_partner",
      "payload": {
        "model": "res.partner",
        "method": "create",
        "values": {
          "name": "Example Corp",
          "email": "contact@example.com",
          "comment": "[Loom Case: abc12345] OSINT investigation target"
        }
      }
    }
  ],
  "case_id": "abc12345",
  "requires_confirmation": true,
  "confirmed": false,
  "created_at": "2026-01-05T10:30:00"
}
```

#### Step 2: Review & Confirm

Review the proposal JSON carefully. Check:
- Operation type (`op`)
- Target model
- Field values
- Case ID for audit trail

#### Step 3: Execute

**Execute the Proposal:**

```bash
POST /odoo/execute/{proposal_id}
```

**Payload:**
```json
{
  "confirmed": true
}
```

**Response:**
```json
{
  "proposal_id": "f8a3b21c",
  "case_id": "abc12345",
  "executed_at": "2026-01-05T10:35:00",
  "results": [
    {
      "op": "upsert_partner",
      "model": "res.partner",
      "method": "create",
      "success": true,
      "record_id": 789
    }
  ]
}
```

---

### Other Proposal Endpoints

#### `POST /odoo/propose/lead`
Propose creating a CRM opportunity.

**Payload:**
```json
{
  "name": "Web Design Project",
  "partner_id": 123,
  "email_from": "john@example.com",
  "phone": "+1234567890",
  "description": "Client wants modern website redesign",
  "expected_revenue": 15000.00,
  "case_id": "abc12345"
}
```

#### `POST /odoo/propose/project`
Propose creating a project.

**Payload:**
```json
{
  "name": "Example Corp Website Redesign",
  "partner_id": 123,
  "user_id": 5,
  "date_start": "2026-02-01",
  "case_id": "abc12345"
}
```

#### `POST /odoo/propose/tasks`
Propose creating multiple tasks.

**Payload:**
```json
{
  "project_id": 45,
  "tasks": [
    {
      "name": "Create design mockups",
      "description": "Initial wireframes and mockups",
      "date_deadline": "2026-02-15",
      "priority": "1"
    },
    {
      "name": "Develop frontend",
      "description": "Implement responsive design",
      "date_deadline": "2026-03-01",
      "priority": "1"
    }
  ],
  "case_id": "abc12345"
}
```

#### `POST /odoo/propose/activity`
Propose scheduling an activity.

**Payload:**
```json
{
  "res_model": "crm.lead",
  "res_id": 67,
  "activity_type": "Call",
  "summary": "Follow up on proposal",
  "date_deadline": "2026-01-10",
  "note": "Discuss project scope and timeline",
  "case_id": "abc12345"
}
```

#### `POST /odoo/propose/calendar-event`
Propose creating a calendar event.

**Payload:**
```json
{
  "name": "Project Kickoff Meeting",
  "start": "2026-02-01T10:00:00",
  "stop": "2026-02-01T11:30:00",
  "partner_ids": [123, 456],
  "location": "Conference Room A",
  "description": "Discuss project scope and timeline",
  "case_id": "abc12345"
}
```

---

### Proposal Management

#### `GET /odoo/proposals`
List all pending proposals.

**Response:**
```json
{
  "count": 3,
  "proposals": [
    { /* proposal 1 */ },
    { /* proposal 2 */ },
    { /* proposal 3 */ }
  ]
}
```

#### `DELETE /odoo/proposals/{proposal_id}`
Cancel a pending proposal.

**Response:**
```json
{
  "status": "cancelled",
  "proposal_id": "f8a3b21c"
}
```

---

## Usage Examples

### Example 1: OSINT Investigation → Odoo Lead

1. **Run OSINT investigation** on `example.com`
2. **Search Odoo** to check if company exists:
   ```bash
   POST /odoo/search/partners
   {"website": "example.com"}
   ```
3. **If not found**, propose creating partner:
   ```bash
   POST /odoo/propose/partner
   {
     "name": "Example Corp",
     "website": "https://example.com",
     "email": "contact@example.com",
     "case_id": "osint-abc123"
   }
   ```
4. **Review proposal** JSON
5. **Confirm and execute**:
   ```bash
   POST /odoo/execute/{proposal_id}
   {"confirmed": true}
   ```
6. **Create opportunity** with OSINT findings:
   ```bash
   POST /odoo/propose/lead
   {
     "name": "OSINT-identified prospect",
     "partner_id": 789,
     "description": "Found via web research...",
     "case_id": "osint-abc123"
   }
   ```

### Example 2: Enriching Existing Contact

1. **Search partner** by email:
   ```bash
   POST /odoo/search/partners
   {"email": "john@example.com"}
   ```
2. **Get full history**:
   ```bash
   GET /odoo/partners/123
   ```
3. **Use history** to inform OSINT investigation strategy
4. **Update findings** by scheduling follow-up:
   ```bash
   POST /odoo/propose/activity
   {
     "res_model": "res.partner",
     "res_id": 123,
     "summary": "Review OSINT findings",
     "date_deadline": "2026-01-15",
     "case_id": "osint-xyz789"
   }
   ```

---

## Security Considerations

### Audit Trail

All Odoo writes include:
- `source='Loom'`
- `case_id` for traceability
- Audit notes in comments/descriptions

### Permissions

The dedicated Loom user should have:
- **READ**: Contacts, CRM, Projects, Tasks, Activities, Calendar
- **WRITE**: Limited to specific operations
- **NO DELETE**: Never allow Loom to delete records

### Confirmation Workflow

The **propose → confirm → execute** pattern ensures:
1. Human review before any data modification
2. Clear visibility into proposed changes
3. Audit trail of who approved what

### Rate Limiting

- READ endpoints: 30 requests/minute
- WRITE endpoints: 10 requests/minute
- Execution endpoint: 10 requests/minute

---

## Troubleshooting

### Connection Issues

**Problem**: `Odoo client not available`

**Solutions**:
1. Check `.env` configuration:
   ```bash
   ODOO_URL=https://ocg.lan
   ODOO_DB=ocg_production
   ODOO_USERNAME=loom@ocg.lan
   ODOO_PASSWORD=your_password
   ```
2. Verify Odoo is accessible:
   ```bash
   curl https://ocg.lan
   ```
3. Check Loom logs:
   ```bash
   docker logs loom-api
   ```

### Authentication Errors

**Problem**: `Authentication failed`

**Solutions**:
1. Verify credentials in Odoo UI
2. Check user has "API Access" enabled
3. Ensure password is correct (no trailing spaces)

### Permission Errors

**Problem**: `Access Denied` when executing proposals

**Solutions**:
1. Check Loom user permissions in Odoo
2. Ensure user has write access to target models
3. Review security groups assigned to user

---

## API Reference Summary

| Endpoint | Method | Purpose | Confirmation Required |
|----------|--------|---------|----------------------|
| `/odoo/status` | GET | Check connection | No |
| `/odoo/search/partners` | POST | Search contacts | No |
| `/odoo/partners/{id}` | GET | Get partner history | No |
| `/odoo/search/leads` | POST | Search opportunities | No |
| `/odoo/search/projects` | POST | Search projects | No |
| `/odoo/search/tasks` | POST | Search tasks | No |
| `/odoo/search/activities` | POST | Search activities | No |
| `/odoo/search/calendar` | POST | Search events | No |
| `/odoo/propose/partner` | POST | Propose partner create/update | **Yes** |
| `/odoo/propose/lead` | POST | Propose opportunity | **Yes** |
| `/odoo/propose/project` | POST | Propose project | **Yes** |
| `/odoo/propose/tasks` | POST | Propose tasks | **Yes** |
| `/odoo/propose/activity` | POST | Propose activity | **Yes** |
| `/odoo/propose/calendar-event` | POST | Propose event | **Yes** |
| `/odoo/execute/{id}` | POST | Execute proposal | **Yes** |
| `/odoo/proposals` | GET | List pending proposals | No |
| `/odoo/proposals/{id}` | DELETE | Cancel proposal | No |

---

## Development

### Running Tests

```bash
# Start Loom with Odoo integration
docker-compose up -d

# Check Odoo status
curl -H "X-API-Key: your_api_key" \
  http://localhost:8787/odoo/status

# Search for a partner
curl -X POST \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}' \
  http://localhost:8787/odoo/search/partners
```

### Adding New Operations

1. Add method to `OdooWriteOperations` in `odoo_client.py`
2. Add proposal endpoint in `main.py`
3. Update this documentation

---

## Changelog

### v1.0.0 (2026-01-05)
- Initial Odoo integration
- XML-RPC client with connection pooling
- READ operations for partners, leads, projects, tasks, activities, calendar
- WRITE operations with proposal/confirmation workflow
- Comprehensive API endpoints
- Security: API key authentication, rate limiting, audit trails
