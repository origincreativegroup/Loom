"""
Loom v2 - OSINT Orchestration Platform
Unified interface for local OSINT tools on pi-net
Production-hardened version with security, monitoring, and reliability features
"""

import os
import json
import uuid
import asyncio
import asyncpg
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from functools import lru_cache

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends, WebSocket, WebSocketDisconnect, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator, constr, EmailStr
from pythonjsonlogger import jsonlogger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import aiofiles

# Import OSINT tool integrations
from osint_tools import ToolRegistry

# Import Odoo integration
from odoo_client import (
    OdooClient,
    OdooReadOperations,
    OdooWriteOperations,
    OdooProposal,
    OdooConnectionError,
    OdooAuthenticationError,
    OdooOperationError
)

# ============================================================================
# Logging Configuration
# ============================================================================

# Configure structured JSON logging for production
log_handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter(
    '%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d'
)
log_handler.setFormatter(formatter)

logger = logging.getLogger("loom")
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)

# Suppress overly verbose logs from libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

# ============================================================================
# Configuration
# ============================================================================

# Core Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.50.157:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
CASES_DIR = DATA_DIR / "cases"
API_KEY = os.getenv("OSINT_API_KEY", "")

# Security Configuration
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8788,http://localhost:3000").split(",")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,loom.lan,*.lan").split(",")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")  # development, staging, production
MAX_TARGET_LENGTH = int(os.getenv("MAX_TARGET_LENGTH", "255"))
MAX_TITLE_LENGTH = int(os.getenv("MAX_TITLE_LENGTH", "200"))
MAX_DESCRIPTION_LENGTH = int(os.getenv("MAX_DESCRIPTION_LENGTH", "1000"))

# Database configuration
COUCHDB_URL = os.getenv("COUCHDB_URL", "https://couchdb.lan")
COUCHDB_USER = os.getenv("COUCHDB_USER", "admin")
COUCHDB_PASS = os.getenv("COUCHDB_PASS", "")
COUCHDB_DB = os.getenv("COUCHDB_DB", "osint_scans")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "192.168.50.168")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5433"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "automation")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASS = os.getenv("POSTGRES_PASS", "")

# Odoo Configuration
ODOO_URL = os.getenv("ODOO_URL", "https://ocg.lan")
ODOO_DB = os.getenv("ODOO_DB", "ocg_production")
ODOO_USERNAME = os.getenv("ODOO_USERNAME", "loom@ocg.lan")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "")
ODOO_SEARCH_FIELDS = os.getenv("ODOO_SEARCH_FIELDS", "email,phone,name,website").split(",")
ODOO_INCLUDE_CUSTOMERS = os.getenv("ODOO_INCLUDE_CUSTOMERS", "true").lower() == "true"
ODOO_INCLUDE_OPPORTUNITIES = os.getenv("ODOO_INCLUDE_OPPORTUNITIES", "true").lower() == "true"

# Ensure data directories exist
CASES_DIR.mkdir(parents=True, exist_ok=True)

# Initialize tool registry
tool_registry = ToolRegistry()

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Global resources
pg_pool = None
http_client = None
health_cache = {"data": None, "expires": None}

# Odoo clients (initialized on startup)
odoo_client = None
odoo_read = None
odoo_write = None
odoo_proposals = {}  # Store pending proposals by ID

# Running case tracking for abort functionality
running_cases = {}  # Maps case_id -> asyncio.Task

# ============================================================================
# Prometheus Metrics
# ============================================================================

# Request metrics
http_requests_total = Counter(
    'loom_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'loom_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

# Business metrics
cases_created_total = Counter(
    'loom_cases_created_total',
    'Total cases created'
)

cases_completed_total = Counter(
    'loom_cases_completed_total',
    'Total cases completed successfully'
)

cases_failed_total = Counter(
    'loom_cases_failed_total',
    'Total cases failed'
)

tools_executed_total = Counter(
    'loom_tools_executed_total',
    'Total OSINT tools executed',
    ['tool_name', 'status']
)

active_cases = Gauge(
    'loom_active_cases',
    'Number of currently active cases'
)

# System metrics
db_connections = Gauge(
    'loom_db_connections',
    'Active database connections',
    ['database']
)

# ============================================================================
# Lifespan Context Manager
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern FastAPI lifespan management for startup/shutdown"""
    global pg_pool, http_client, odoo_client, odoo_read, odoo_write

    # Startup
    logger.info("🚀 Starting Loom OSINT Orchestration Platform...")

    # Initialize PostgreSQL connection pool
    try:
        pg_pool = await asyncpg.create_pool(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASS,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        logger.info("✅ PostgreSQL connection pool established")
    except Exception as e:
        logger.warning(f"⚠️  PostgreSQL unavailable: {e}")

    # Initialize shared HTTP client with connection pooling
    # Note: verify=False for internal .lan domains - in production with proper certs, set verify=True
    ssl_verify = ENVIRONMENT == "production"
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        verify=ssl_verify,
        follow_redirects=True
    )
    logger.info(f"✅ HTTP client initialized (SSL verify: {ssl_verify})")

    # Initialize Odoo client
    if ODOO_URL and ODOO_USERNAME and ODOO_PASSWORD:
        try:
            odoo_client = OdooClient(
                url=ODOO_URL,
                db=ODOO_DB,
                username=ODOO_USERNAME,
                password=ODOO_PASSWORD
            )
            # Test authentication
            odoo_client.authenticate()
            odoo_read = OdooReadOperations(odoo_client)
            odoo_write = OdooWriteOperations(odoo_client)
            logger.info("✅ Odoo client initialized and authenticated")
        except Exception as e:
            logger.warning(f"⚠️  Odoo unavailable: {e}")
            odoo_client = None
            odoo_read = None
            odoo_write = None
    else:
        logger.info("ℹ️  Odoo credentials not configured - skipping initialization")

    logger.info("✅ Loom initialization complete")

    yield

    # Shutdown
    logger.info("🔄 Shutting down Loom...")

    if pg_pool:
        await pg_pool.close()
        logger.info("✅ PostgreSQL pool closed")

    if http_client:
        await http_client.aclose()
        logger.info("✅ HTTP client closed")

    logger.info("👋 Loom shutdown complete")

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Loom OSINT Orchestration Platform",
    description="Unified interface for local OSINT tools",
    version="2.1.0",
    lifespan=lifespan,
    docs_url="/docs" if ENVIRONMENT != "production" else None,  # Disable docs in production
    redoc_url="/redoc" if ENVIRONMENT != "production" else None
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - Restrict origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

# Trusted hosts middleware - prevent host header attacks
if ENVIRONMENT == "production":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


# ============================================================================
# Security Middleware
# ============================================================================

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    # HSTS for production
    if ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # CSP
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )

    return response


@app.middleware("http")
async def request_tracking_middleware(request: Request, call_next):
    """Add request ID tracking and metrics"""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # Add request ID to logging context
    with logger.contextualize(request_id=request_id):
        start_time = datetime.utcnow()

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id

            # Record metrics
            duration = (datetime.utcnow() - start_time).total_seconds()
            http_requests_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code
            ).inc()

            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(duration)

            logger.info(
                f"{request.method} {request.url.path}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_seconds": duration,
                    "request_id": request_id,
                    "client_ip": request.client.host if request.client else "unknown"
                }
            )

            return response

        except Exception as e:
            logger.error(
                f"Request failed: {str(e)}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e)
                },
                exc_info=True
            )
            raise


# Monkeypatch logger.contextualize if not available
if not hasattr(logger, 'contextualize'):
    from contextlib import contextmanager
    @contextmanager
    def contextualize(self, **kwargs):
        yield
    logger.contextualize = lambda **kwargs: contextualize(logger, **kwargs)

# ============================================================================
# Security
# ============================================================================

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify API key if configured"""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True

# ============================================================================
# Input Validation Helpers
# ============================================================================

def sanitize_string(value: str) -> str:
    """Sanitize user input to prevent injection attacks"""
    if not value:
        return value
    # Remove control characters and potential injection patterns
    value = re.sub(r'[\x00-\x1F\x7F]', '', value)
    # Remove common injection patterns
    dangerous_patterns = [';', '&&', '||', '`', '$(',  '${']
    for pattern in dangerous_patterns:
        if pattern in value:
            raise ValueError(f"Input contains potentially dangerous pattern: {pattern}")
    return value.strip()


def validate_target(value: str) -> str:
    """Validate OSINT target format"""
    value = sanitize_string(value)

    # Check length
    if len(value) > MAX_TARGET_LENGTH:
        raise ValueError(f"Target exceeds maximum length of {MAX_TARGET_LENGTH}")

    # Validate format: domain, IP, email, or username
    # Domain/subdomain pattern
    domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    # IP address pattern
    ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    # Email pattern (basic)
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    # Username pattern (alphanumeric with limited special chars)
    username_pattern = r'^[a-zA-Z0-9_\-\.]{3,50}$'

    if not (re.match(domain_pattern, value) or
            re.match(ip_pattern, value) or
            re.match(email_pattern, value) or
            re.match(username_pattern, value)):
        raise ValueError(
            "Target must be a valid domain, IP address, email, or username"
        )

    return value


# ============================================================================
# Models
# ============================================================================

class ToolSelection(BaseModel):
    """Tool selection and options"""
    name: constr(min_length=1, max_length=50)
    enabled: bool = True
    options: Dict[str, Any] = Field(default_factory=dict)

    @validator('name')
    def validate_tool_name(cls, v):
        # Only allow alphanumeric and hyphens
        if not re.match(r'^[a-z0-9\-]+$', v):
            raise ValueError("Tool name must contain only lowercase letters, numbers, and hyphens")
        return v


class CaseCreate(BaseModel):
    """Request to create a new case"""
    title: constr(min_length=1, max_length=MAX_TITLE_LENGTH) = Field(
        ...,
        description="Case title/subject"
    )
    description: Optional[constr(max_length=MAX_DESCRIPTION_LENGTH)] = Field(
        None,
        description="Case description"
    )
    target: constr(min_length=3, max_length=MAX_TARGET_LENGTH) = Field(
        ...,
        description="Investigation target (domain, IP, username, etc.)"
    )
    tools: List[constr(min_length=1, max_length=50)] = Field(
        default=["searxng"],
        description="Tools to execute: searxng, recon-ng, theharvester, sherlock, spiderfoot, intelowl",
        min_items=1,
        max_items=10
    )
    tool_options: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-tool configuration options"
    )

    @validator('title', 'description')
    def sanitize_text_fields(cls, v):
        if v:
            return sanitize_string(v)
        return v

    @validator('target')
    def validate_target_field(cls, v):
        return validate_target(v)

    @validator('tools')
    def validate_tools_list(cls, v):
        allowed_tools = {'searxng', 'recon-ng', 'theharvester', 'sherlock', 'spiderfoot', 'intelowl'}
        for tool in v:
            if tool not in allowed_tools:
                raise ValueError(f"Unknown tool: {tool}. Allowed tools: {', '.join(allowed_tools)}")
        return v

class PipelineStatus(BaseModel):
    """Pipeline execution status"""
    case_id: str
    status: str
    stage: str
    tools_completed: List[str] = Field(default_factory=list)
    tools_failed: List[str] = Field(default_factory=list)
    message: Optional[str] = None
    report_ready: bool = False

class CaseInfo(BaseModel):
    """Case metadata"""
    case_id: str
    title: str
    description: Optional[str]
    target: str
    tools_used: List[str]
    created_at: str
    status: str

class ToolStatus(BaseModel):
    """Individual tool status"""
    name: str
    enabled: bool
    status: str
    results_count: int
    error: Optional[str]

# ============================================================================
# Database Functions
# ============================================================================

async def log_to_postgres(case_id: str, tool_name: str, status: str, step: str, details: Dict[str, Any] = None):
    """Log activity to PostgreSQL osint_logs table with error handling"""
    if not pg_pool:
        logger.debug("PostgreSQL pool not available, skipping log")
        return

    try:
        async with pg_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO osint_logs (correlation_id, tool_name, status, step, details, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, case_id, tool_name, status, step, json.dumps(details or {}), datetime.utcnow())
        logger.debug(f"Logged to PostgreSQL: {case_id}/{tool_name}/{step}")
    except Exception as e:
        logger.error(f"PostgreSQL log error for {case_id}: {e}")

async def save_to_couchdb(case_id: str, case_data: Dict[str, Any]):
    """Save case to CouchDB osint_scans database with retry logic"""
    max_retries = 3

    for attempt in range(max_retries):
        try:
            # Use shared HTTP client if available, otherwise create temporary one
            client_to_use = http_client if http_client else httpx.AsyncClient(timeout=30.0, verify=False)

            try:
                response = await client_to_use.put(
                    f"{COUCHDB_URL}/{COUCHDB_DB}/{case_id}",
                    json=case_data,
                    auth=(COUCHDB_USER, COUCHDB_PASS) if COUCHDB_USER else None
                )

                if response.status_code in [201, 202]:
                    logger.info(f"✅ Case {case_id} saved to CouchDB")
                    return
                else:
                    logger.warning(f"CouchDB save failed (attempt {attempt + 1}): {response.status_code}")

            finally:
                # Close temporary client if we created one
                if client_to_use != http_client:
                    await client_to_use.aclose()

        except Exception as e:
            logger.error(f"CouchDB save error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

    logger.error(f"❌ Failed to save case {case_id} to CouchDB after {max_retries} attempts")

# ============================================================================
# Ollama Integration
# ============================================================================

async def call_ollama(prompt: str, system: Optional[str] = None, json_mode: bool = False) -> str:
    """Call Ollama API for LLM generation"""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            }

            if system:
                payload["system"] = system

            if json_mode:
                payload["format"] = "json"

            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ollama API error: {str(e)}"
        )

async def synthesize_unified_report(case_data: Dict[str, Any], tool_results: List[Dict[str, Any]]) -> str:
    """Synthesize results from multiple OSINT tools into unified report"""

    system_prompt = """You are an expert OSINT analyst. Synthesize the provided results from multiple OSINT tools into a comprehensive, well-structured intelligence report.

The results come from various tools (SearXNG, Recon-ng, TheHarvester, Sherlock, SpiderFoot, IntelOwl).

Format your report in markdown with:
- Executive Summary
- Key Findings (organized by category: Infrastructure, People, Social Media, Threats, etc.)
- Tool-by-Tool Analysis
- Cross-Reference Analysis (correlations between different tool findings)
- Recommendations
- Sources

Be factual, cite the tool that provided each finding, and highlight information gaps."""

    # Organize results by tool
    results_text = "\n\n".join([
        f"## {result.get('tool', 'Unknown Tool').upper()} Results\n" +
        f"**Status:** {result.get('status', 'unknown')}\n" +
        f"**Results Count:** {len(result.get('results', []))}\n" +
        (f"**Error:** {result.get('error')}\n" if result.get('error') else "") +
        "\n### Findings:\n" +
        json.dumps(result.get('results', [])[:50], indent=2)  # Limit to 50 results per tool
        for result in tool_results
    ])

    user_prompt = f"""Target: {case_data.get('target')}
Case: {case_data.get('title')}
Description: {case_data.get('description', 'N/A')}

Tool Results:
{results_text}

Generate a comprehensive unified OSINT intelligence report."""

    report = await call_ollama(user_prompt, system=system_prompt)
    return report

# ============================================================================
# Case Management
# ============================================================================

def create_case_directory(case_id: str) -> Path:
    """Create case directory structure"""
    case_dir = CASES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "raw").mkdir(exist_ok=True)
    (case_dir / "tools").mkdir(exist_ok=True)
    return case_dir

async def save_case_metadata(case_id: str, metadata: Dict[str, Any]):
    """Save case metadata to case.json"""
    case_dir = CASES_DIR / case_id
    case_file = case_dir / "case.json"

    async with aiofiles.open(case_file, "w") as f:
        await f.write(json.dumps(metadata, indent=2))

async def load_case_metadata(case_id: str) -> Optional[Dict[str, Any]]:
    """Load case metadata from case.json"""
    case_file = CASES_DIR / case_id / "case.json"

    if not case_file.exists():
        return None

    async with aiofiles.open(case_file, "r") as f:
        content = await f.read()
        return json.loads(content)

async def save_tool_results(case_id: str, tool_name: str, results: Dict[str, Any]):
    """Save individual tool results"""
    case_dir = CASES_DIR / case_id
    tool_file = case_dir / "tools" / f"{tool_name}.json"

    async with aiofiles.open(tool_file, "w") as f:
        await f.write(json.dumps(results, indent=2))

async def save_report(case_id: str, report: str):
    """Save final unified markdown report"""
    case_dir = CASES_DIR / case_id
    report_file = case_dir / "report.md"

    async with aiofiles.open(report_file, "w") as f:
        await f.write(report)

# ============================================================================
# OSINT Pipeline Orchestration
# ============================================================================

async def run_osint_pipeline(case_id: str, case_create: CaseCreate) -> Dict[str, Any]:
    """
    Execute the unified OSINT pipeline:
    1. Create case
    2. Execute selected tools in parallel
    3. Synthesize unified report with Ollama
    4. Save results to filesystem, CouchDB, and PostgreSQL
    5. Return case metadata

    Supports cancellation via asyncio.CancelledError
    """

    try:
        # 1. Create case structure
        create_case_directory(case_id)

        case_metadata = {
            "case_id": case_id,
            "title": case_create.title,
            "description": case_create.description,
            "target": case_create.target,
            "tools_requested": case_create.tools,
            "created_at": datetime.utcnow().isoformat(),
            "status": "processing"
        }

        await save_case_metadata(case_id, case_metadata)
        await log_to_postgres(case_id, "loom", "started", "case_created", case_metadata)

        # 2. Execute tools
        await log_to_postgres(case_id, "loom", "running", "executing_tools", {"tools": case_create.tools})

        tool_results = await tool_registry.execute_tools(
            case_create.target,
            case_create.tools,
            case_create.tool_options
        )

        # Save individual tool results
        for result in tool_results:
            tool_name = result.get("tool", "unknown")
            await save_tool_results(case_id, tool_name, result)
            await log_to_postgres(
                case_id,
                tool_name,
                result.get("status", "unknown"),
                "tool_completed",
                {"results_count": len(result.get("results", []))}
            )

        case_metadata["tool_results"] = tool_results
        case_metadata["status"] = "synthesizing"
        await save_case_metadata(case_id, case_metadata)

        # 3. Synthesize unified report
        await log_to_postgres(case_id, "loom", "running", "synthesizing_report")

        report = await synthesize_unified_report(case_metadata, tool_results)
        await save_report(case_id, report)

        # 4. Mark complete
        case_metadata["status"] = "completed"
        case_metadata["completed_at"] = datetime.utcnow().isoformat()
        await save_case_metadata(case_id, case_metadata)

        # 5. Save to CouchDB
        await save_to_couchdb(case_id, case_metadata)
        await log_to_postgres(case_id, "loom", "completed", "pipeline_finished")

        return case_metadata

    except asyncio.CancelledError:
        # Handle graceful cancellation/abort
        logger.info(f"⚠️  Case {case_id} aborted by user")

        case_metadata["status"] = "aborted"
        case_metadata["aborted_at"] = datetime.utcnow().isoformat()
        await save_case_metadata(case_id, case_metadata)
        await log_to_postgres(case_id, "loom", "aborted", "pipeline_aborted", {"reason": "user_request"})

        raise  # Re-raise to signal abortion

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
@limiter.limit("60/minute")
async def root(request: Request):
    """Health check"""
    return {
        "service": "Loom OSINT Orchestration Platform",
        "status": "operational",
        "version": "2.1.0",
        "environment": ENVIRONMENT
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
async def health():
    """Health check with service status and caching (30s TTL)"""
    global health_cache

    # Check cache
    now = datetime.utcnow()
    if health_cache["data"] and health_cache["expires"] and now < health_cache["expires"]:
        logger.debug("Returning cached health status")
        return health_cache["data"]

    health_status = {
        "api": "ok",
        "ollama": "unknown",
        "postgres": "ok" if pg_pool else "disabled",
        "couchdb": "unknown"
    }

    # Check Ollama
    try:
        if http_client:
            response = await http_client.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        else:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{OLLAMA_URL}/api/tags")

        if response.status_code == 200:
            health_status["ollama"] = "ok"
            logger.debug("Ollama service: OK")
        else:
            health_status["ollama"] = "error"
    except Exception as e:
        health_status["ollama"] = "error"
        logger.debug(f"Ollama service error: {e}")

    # Check CouchDB
    try:
        if http_client:
            response = await http_client.get(
                f"{COUCHDB_URL}/{COUCHDB_DB}",
                auth=(COUCHDB_USER, COUCHDB_PASS) if COUCHDB_USER else None,
                timeout=5.0
            )
        else:
            async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
                response = await client.get(
                    f"{COUCHDB_URL}/{COUCHDB_DB}",
                    auth=(COUCHDB_USER, COUCHDB_PASS) if COUCHDB_USER else None
                )

        if response.status_code == 200:
            health_status["couchdb"] = "ok"
            logger.debug("CouchDB service: OK")
        else:
            health_status["couchdb"] = "error"
    except Exception as e:
        health_status["couchdb"] = "error"
        logger.debug(f"CouchDB service error: {e}")

    # Cache for 30 seconds
    health_cache["data"] = health_status
    health_cache["expires"] = now + timedelta(seconds=30)

    return health_status

@app.get("/tools", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def list_tools(request: Request):
    """List all available OSINT tools and their status"""
    return {
        "tools": tool_registry.get_all_tools_status()
    }

async def _execute_pipeline_background(case_id: str, case_create: CaseCreate):
    """Background task to execute pipeline with cleanup"""
    try:
        await run_osint_pipeline(case_id, case_create)

        tools_completed = []
        tools_failed = []

        case_metadata = await load_case_metadata(case_id)
        for result in case_metadata.get("tool_results", []):
            if result.get("status") == "success":
                tools_completed.append(result.get("tool"))
                tools_executed_total.labels(tool_name=result.get("tool"), status="success").inc()
            else:
                tools_failed.append(result.get("tool"))
                tools_executed_total.labels(tool_name=result.get("tool"), status="error").inc()

        logger.info(f"✅ Case {case_id} completed: {len(tools_completed)} succeeded, {len(tools_failed)} failed")
        cases_completed_total.inc()

    except asyncio.CancelledError:
        logger.info(f"⚠️  Case {case_id} aborted")
        # Metadata already updated in run_osint_pipeline

    except Exception as e:
        logger.error(f"❌ Case {case_id} failed: {e}", exc_info=True)
        await log_to_postgres(case_id, "loom", "error", "pipeline_failed", {"error": str(e)})
        cases_failed_total.inc()

    finally:
        # Clean up task tracking
        active_cases.dec()
        if case_id in running_cases:
            del running_cases[case_id]


@app.post("/cases", response_model=PipelineStatus, dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")  # Limit case creation to prevent abuse
async def create_case(request: Request, case_create: CaseCreate):
    """Create a new case and run the OSINT orchestration pipeline in background"""

    case_id = str(uuid.uuid4())[:8]
    logger.info(f"🔍 Creating new case {case_id}: {case_create.title}")

    # Track metrics
    cases_created_total.inc()
    active_cases.inc()

    # Create and track background task
    task = asyncio.create_task(_execute_pipeline_background(case_id, case_create))
    running_cases[case_id] = task

    # Return immediate response - client should poll for status
    return PipelineStatus(
        case_id=case_id,
        status="processing",
        stage="pipeline_started",
        tools_completed=[],
        tools_failed=[],
        message="Pipeline execution started. Poll /cases/{case_id} for status.",
        report_ready=False
    )

@app.get("/cases", dependencies=[Depends(verify_api_key)])
@limiter.limit("60/minute")
async def list_cases(request: Request):
    """List all cases"""
    cases = []

    for case_dir in CASES_DIR.iterdir():
        if case_dir.is_dir():
            metadata = await load_case_metadata(case_dir.name)
            if metadata:
                cases.append(CaseInfo(
                    case_id=metadata["case_id"],
                    title=metadata["title"],
                    description=metadata.get("description"),
                    target=metadata.get("target", "N/A"),
                    tools_used=metadata.get("tools_requested", []),
                    created_at=metadata["created_at"],
                    status=metadata.get("status", "unknown")
                ))

    return {"cases": cases}

@app.get("/cases/{case_id}", dependencies=[Depends(verify_api_key)])
@limiter.limit("60/minute")
async def get_case(request: Request, case_id: str):
    """Get case details"""
    metadata = await load_case_metadata(case_id)

    if not metadata:
        raise HTTPException(status_code=404, detail="Case not found")

    return metadata

@app.post("/cases/{case_id}/abort", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def abort_case(request: Request, case_id: str):
    """Abort a running case execution"""

    # Check if case is currently running
    if case_id not in running_cases:
        # Check if case exists but isn't running
        metadata = await load_case_metadata(case_id)
        if metadata:
            status = metadata.get("status", "unknown")
            if status in ["completed", "aborted", "failed"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Case {case_id} is not running (status: {status})"
                )
        raise HTTPException(status_code=404, detail=f"No running case found with ID {case_id}")

    # Cancel the running task
    task = running_cases[case_id]
    task.cancel()

    logger.info(f"🛑 Abort requested for case {case_id}")

    return {
        "case_id": case_id,
        "status": "aborting",
        "message": "Case execution is being aborted. Check case status for updates."
    }

@app.get("/cases/{case_id}/report", dependencies=[Depends(verify_api_key)])
@limiter.limit("60/minute")
async def get_report(request: Request, case_id: str):
    """Get case report"""
    report_file = CASES_DIR / case_id / "report.md"

    if not report_file.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    async with aiofiles.open(report_file, "r") as f:
        report = await f.read()

    return {"case_id": case_id, "report": report}

@app.get("/cases/{case_id}/tools/{tool_name}", dependencies=[Depends(verify_api_key)])
@limiter.limit("60/minute")
async def get_tool_results(request: Request, case_id: str, tool_name: str):
    """Get results from a specific tool"""
    tool_file = CASES_DIR / case_id / "tools" / f"{tool_name}.json"

    if not tool_file.exists():
        raise HTTPException(status_code=404, detail=f"Results for {tool_name} not found")

    async with aiofiles.open(tool_file, "r") as f:
        results = await f.read()

    return json.loads(results)

@app.get("/config")
async def get_config():
    """Get public configuration (for UI)"""
    return {
        "ollama_url": OLLAMA_URL,
        "ollama_model": OLLAMA_MODEL,
        "available_tools": [
            {"name": "searxng", "description": "Web search via SearXNG"},
            {"name": "recon-ng", "description": "Reconnaissance framework (subdomains, hosts)"},
            {"name": "theharvester", "description": "Email and subdomain harvesting"},
            {"name": "sherlock", "description": "Username search across social media"},
            {"name": "spiderfoot", "description": "OSINT automation framework"},
            {"name": "intelowl", "description": "Threat intelligence platform"}
        ],
        "api_key_required": bool(API_KEY),
        "databases": {
            "couchdb": bool(COUCHDB_URL),
            "postgres": bool(pg_pool)
        }
    }

@app.post("/chat", dependencies=[Depends(verify_api_key)])
@limiter.limit("20/minute")  # More restrictive for AI endpoints
async def chat_with_assistant(request: Request, payload: Dict[str, Any]):
    """
    AI Research Assistant endpoint - helps with target research and OSINT strategy
    """
    user_message = payload.get("message", "")
    context = payload.get("context", {})  # Can include current target, case info, etc.

    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")

    logger.info(f"💬 AI Assistant query: {user_message[:100]}...")

    system_prompt = """You are an expert OSINT (Open Source Intelligence) research assistant integrated into the Loom platform.

Your role is to help investigators with:
1. **Target Research Strategy**: Suggest which OSINT tools to use based on target type (domain, IP, username, email, etc.)
2. **Data Orchestration**: Help correlate findings from multiple tools
3. **Investigation Planning**: Guide users through methodical OSINT workflows
4. **Tool Selection**: Recommend the best tools from Loom's arsenal (SearXNG, Recon-ng, TheHarvester, Sherlock, SpiderFoot, IntelOwl)
5. **Best Practices**: Share OSINT techniques, legal considerations, and operational security tips

Available tools in Loom:
- **SearXNG**: Web search aggregation
- **Recon-ng**: Subdomain enumeration and reconnaissance
- **TheHarvester**: Email and subdomain harvesting from public sources
- **Sherlock**: Username search across 300+ social media platforms
- **SpiderFoot**: Automated OSINT framework with 200+ modules
- **IntelOwl**: Threat intelligence analysis

Be concise, practical, and actionable. If the user mentions a specific target, suggest relevant tools and investigation approaches."""

    # Build context-aware prompt
    full_prompt = user_message
    if context:
        if context.get("target"):
            full_prompt = f"Target: {context['target']}\n\nQuestion: {user_message}"
        if context.get("tools_used"):
            full_prompt += f"\n\nTools already used: {', '.join(context['tools_used'])}"

    try:
        response = await call_ollama(full_prompt, system=system_prompt)

        logger.info("✅ AI Assistant response generated")

        return {
            "response": response,
            "model": OLLAMA_MODEL,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ AI Assistant error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"AI Assistant error: {str(e)}"
        )

# ============================================================================
# Odoo Integration Endpoints
# ============================================================================

@app.get("/odoo/status", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def odoo_status(request: Request):
    """Check Odoo connection status"""
    if not odoo_client:
        return {
            "connected": False,
            "error": "Odoo client not configured"
        }

    try:
        version = odoo_client.get_version()
        return {
            "connected": True,
            "odoo_version": version.get("server_version"),
            "database": ODOO_DB,
            "username": ODOO_USERNAME
        }
    except Exception as e:
        logger.error(f"Odoo status check failed: {e}")
        return {
            "connected": False,
            "error": str(e)
        }


@app.post("/odoo/search/partners", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def search_odoo_partners(request: Request, payload: Dict[str, Any]):
    """
    Search for partners (contacts/companies) in Odoo.

    Payload:
        query: General search query
        email: Search by email
        phone: Search by phone
        website: Search by website/domain
        is_company: Filter companies (true) or individuals (false)
        limit: Maximum results (default 100)
    """
    if not odoo_read:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        results = odoo_read.search_partners(
            query=payload.get("query"),
            email=payload.get("email"),
            phone=payload.get("phone"),
            website=payload.get("website"),
            is_company=payload.get("is_company"),
            limit=payload.get("limit", 100)
        )

        logger.info(f"Found {len(results)} partners in Odoo")
        return {
            "count": len(results),
            "partners": results
        }

    except Exception as e:
        logger.error(f"Odoo partner search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/odoo/partners/{partner_id}", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def get_odoo_partner(request: Request, partner_id: int):
    """Get full details and history for a specific partner"""
    if not odoo_read:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        history = odoo_read.get_partner_history(partner_id)
        logger.info(f"Retrieved history for partner {partner_id}")
        return history

    except Exception as e:
        logger.error(f"Odoo partner retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/search/leads", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def search_odoo_leads(request: Request, payload: Dict[str, Any]):
    """Search for CRM leads/opportunities in Odoo"""
    if not odoo_read:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        results = odoo_read.search_leads(
            partner_id=payload.get("partner_id"),
            email=payload.get("email"),
            name=payload.get("name"),
            stage=payload.get("stage"),
            limit=payload.get("limit", 100)
        )

        logger.info(f"Found {len(results)} leads in Odoo")
        return {
            "count": len(results),
            "leads": results
        }

    except Exception as e:
        logger.error(f"Odoo lead search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/search/projects", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def search_odoo_projects(request: Request, payload: Dict[str, Any]):
    """Search for projects in Odoo"""
    if not odoo_read:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        results = odoo_read.search_projects(
            partner_id=payload.get("partner_id"),
            name=payload.get("name"),
            limit=payload.get("limit", 100)
        )

        logger.info(f"Found {len(results)} projects in Odoo")
        return {
            "count": len(results),
            "projects": results
        }

    except Exception as e:
        logger.error(f"Odoo project search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/search/tasks", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def search_odoo_tasks(request: Request, payload: Dict[str, Any]):
    """Search for project tasks in Odoo"""
    if not odoo_read:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        results = odoo_read.search_tasks(
            project_id=payload.get("project_id"),
            partner_id=payload.get("partner_id"),
            name=payload.get("name"),
            limit=payload.get("limit", 100)
        )

        logger.info(f"Found {len(results)} tasks in Odoo")
        return {
            "count": len(results),
            "tasks": results
        }

    except Exception as e:
        logger.error(f"Odoo task search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/search/activities", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def search_odoo_activities(request: Request, payload: Dict[str, Any]):
    """Search for activities (planned actions) in Odoo"""
    if not odoo_read:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        results = odoo_read.search_activities(
            partner_id=payload.get("partner_id"),
            res_model=payload.get("res_model"),
            res_id=payload.get("res_id"),
            limit=payload.get("limit", 100)
        )

        logger.info(f"Found {len(results)} activities in Odoo")
        return {
            "count": len(results),
            "activities": results
        }

    except Exception as e:
        logger.error(f"Odoo activity search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/search/calendar", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def search_odoo_calendar(request: Request, payload: Dict[str, Any]):
    """Search for calendar events in Odoo"""
    if not odoo_read:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        results = odoo_read.search_calendar_events(
            partner_ids=payload.get("partner_ids"),
            name=payload.get("name"),
            limit=payload.get("limit", 100)
        )

        logger.info(f"Found {len(results)} calendar events in Odoo")
        return {
            "count": len(results),
            "events": results
        }

    except Exception as e:
        logger.error(f"Odoo calendar search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/propose/partner", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def propose_odoo_partner(request: Request, payload: Dict[str, Any]):
    """
    Propose creating/updating a partner in Odoo.
    Returns a JSON proposal that requires confirmation.
    """
    if not odoo_write:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        proposal = odoo_write.propose_upsert_partner(
            name=payload["name"],
            email=payload.get("email"),
            phone=payload.get("phone"),
            website=payload.get("website"),
            is_company=payload.get("is_company", True),
            street=payload.get("street"),
            city=payload.get("city"),
            country_code=payload.get("country_code"),
            comment=payload.get("comment"),
            case_id=payload.get("case_id")
        )

        # Store proposal for later execution
        odoo_proposals[proposal.proposal_id] = proposal

        logger.info(f"Created Odoo proposal {proposal.proposal_id}")
        return proposal.to_json()

    except Exception as e:
        logger.error(f"Odoo proposal creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/propose/lead", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def propose_odoo_lead(request: Request, payload: Dict[str, Any]):
    """Propose creating a CRM lead/opportunity in Odoo"""
    if not odoo_write:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        proposal = odoo_write.propose_create_lead(
            name=payload["name"],
            partner_id=payload.get("partner_id"),
            email_from=payload.get("email_from"),
            phone=payload.get("phone"),
            description=payload.get("description"),
            expected_revenue=payload.get("expected_revenue"),
            case_id=payload.get("case_id")
        )

        odoo_proposals[proposal.proposal_id] = proposal
        logger.info(f"Created Odoo lead proposal {proposal.proposal_id}")
        return proposal.to_json()

    except Exception as e:
        logger.error(f"Odoo lead proposal creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/propose/project", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def propose_odoo_project(request: Request, payload: Dict[str, Any]):
    """Propose creating a project in Odoo"""
    if not odoo_write:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        from datetime import date
        date_start = None
        if payload.get("date_start"):
            date_start = date.fromisoformat(payload["date_start"])

        proposal = odoo_write.propose_create_project(
            name=payload["name"],
            partner_id=payload.get("partner_id"),
            user_id=payload.get("user_id"),
            date_start=date_start,
            case_id=payload.get("case_id")
        )

        odoo_proposals[proposal.proposal_id] = proposal
        logger.info(f"Created Odoo project proposal {proposal.proposal_id}")
        return proposal.to_json()

    except Exception as e:
        logger.error(f"Odoo project proposal creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/propose/tasks", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def propose_odoo_tasks(request: Request, payload: Dict[str, Any]):
    """Propose creating tasks in a project"""
    if not odoo_write:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        proposal = odoo_write.propose_create_tasks(
            project_id=payload["project_id"],
            tasks=payload["tasks"],
            case_id=payload.get("case_id")
        )

        odoo_proposals[proposal.proposal_id] = proposal
        logger.info(f"Created Odoo tasks proposal {proposal.proposal_id}")
        return proposal.to_json()

    except Exception as e:
        logger.error(f"Odoo tasks proposal creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/propose/activity", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def propose_odoo_activity(request: Request, payload: Dict[str, Any]):
    """Propose scheduling an activity"""
    if not odoo_write:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        from datetime import date
        date_deadline = date.fromisoformat(payload["date_deadline"])

        proposal = odoo_write.propose_schedule_activity(
            res_model=payload["res_model"],
            res_id=payload["res_id"],
            activity_type=payload.get("activity_type", "To Do"),
            summary=payload["summary"],
            date_deadline=date_deadline,
            user_id=payload.get("user_id"),
            note=payload.get("note"),
            case_id=payload.get("case_id")
        )

        odoo_proposals[proposal.proposal_id] = proposal
        logger.info(f"Created Odoo activity proposal {proposal.proposal_id}")
        return proposal.to_json()

    except Exception as e:
        logger.error(f"Odoo activity proposal creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/propose/calendar-event", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def propose_odoo_calendar_event(request: Request, payload: Dict[str, Any]):
    """Propose creating a calendar event"""
    if not odoo_write:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    try:
        from datetime import datetime
        start = datetime.fromisoformat(payload["start"])
        stop = datetime.fromisoformat(payload["stop"])

        proposal = odoo_write.propose_create_calendar_event(
            name=payload["name"],
            start=start,
            stop=stop,
            partner_ids=payload.get("partner_ids"),
            location=payload.get("location"),
            description=payload.get("description"),
            case_id=payload.get("case_id")
        )

        odoo_proposals[proposal.proposal_id] = proposal
        logger.info(f"Created Odoo calendar event proposal {proposal.proposal_id}")
        return proposal.to_json()

    except Exception as e:
        logger.error(f"Odoo calendar event proposal creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/odoo/execute/{proposal_id}", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def execute_odoo_proposal(request: Request, proposal_id: str, payload: Dict[str, Any]):
    """
    Execute a confirmed Odoo proposal.

    Requires explicit confirmation in payload: {"confirmed": true}
    """
    if not odoo_write:
        raise HTTPException(status_code=503, detail="Odoo client not available")

    # Check for explicit confirmation
    if not payload.get("confirmed"):
        raise HTTPException(
            status_code=400,
            detail="Proposal execution requires explicit confirmation: {\"confirmed\": true}"
        )

    # Retrieve proposal
    proposal = odoo_proposals.get(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")

    try:
        # Mark as confirmed
        proposal.confirm()

        # Execute
        results = odoo_write.execute_proposal(proposal)

        # Remove from pending proposals
        del odoo_proposals[proposal_id]

        logger.info(f"Executed Odoo proposal {proposal_id}")
        return results

    except Exception as e:
        logger.error(f"Odoo proposal execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/odoo/proposals", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def list_odoo_proposals(request: Request):
    """List all pending Odoo proposals"""
    return {
        "count": len(odoo_proposals),
        "proposals": [p.to_json() for p in odoo_proposals.values()]
    }


@app.delete("/odoo/proposals/{proposal_id}", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def cancel_odoo_proposal(request: Request, proposal_id: str):
    """Cancel a pending Odoo proposal"""
    if proposal_id not in odoo_proposals:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")

    del odoo_proposals[proposal_id]
    logger.info(f"Cancelled Odoo proposal {proposal_id}")
    return {"status": "cancelled", "proposal_id": proposal_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8787)
