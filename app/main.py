"""
Loom v2 - OSINT Orchestration Platform
Unified interface for local OSINT tools on pi-net
"""

import os
import json
import uuid
import asyncpg
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import aiofiles

# Import OSINT tool integrations
from osint_tools import ToolRegistry

# ============================================================================
# Configuration
# ============================================================================

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.50.157:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
CASES_DIR = DATA_DIR / "cases"
API_KEY = os.getenv("OSINT_API_KEY", "")

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

# Ensure data directories exist
CASES_DIR.mkdir(parents=True, exist_ok=True)

# Initialize tool registry
tool_registry = ToolRegistry()

# PostgreSQL connection pool
pg_pool = None

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Loom OSINT Orchestration Platform",
    description="Unified interface for local OSINT tools",
    version="2.0.0"
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize database connections"""
    global pg_pool
    try:
        pg_pool = await asyncpg.create_pool(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASS,
            min_size=1,
            max_size=5
        )
    except Exception as e:
        print(f"Warning: Could not connect to PostgreSQL: {e}")

@app.on_event("shutdown")
async def shutdown():
    """Close database connections"""
    if pg_pool:
        await pg_pool.close()

# ============================================================================
# Security
# ============================================================================

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify API key if configured"""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True

# ============================================================================
# Models
# ============================================================================

class ToolSelection(BaseModel):
    """Tool selection and options"""
    name: str
    enabled: bool = True
    options: Dict[str, Any] = Field(default_factory=dict)

class CaseCreate(BaseModel):
    """Request to create a new case"""
    title: str = Field(..., description="Case title/subject")
    description: Optional[str] = Field(None, description="Case description")
    target: str = Field(..., description="Investigation target (domain, IP, username, etc.)")
    tools: List[str] = Field(
        default=["searxng"],
        description="Tools to execute: searxng, recon-ng, theharvester, sherlock, spiderfoot, intelowl"
    )
    tool_options: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-tool configuration options"
    )

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
    """Log activity to PostgreSQL osint_logs table"""
    if not pg_pool:
        return

    try:
        async with pg_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO osint_logs (correlation_id, tool_name, status, step, details, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, case_id, tool_name, status, step, json.dumps(details or {}), datetime.utcnow())
    except Exception as e:
        print(f"PostgreSQL log error: {e}")

async def save_to_couchdb(case_id: str, case_data: Dict[str, Any]):
    """Save case to CouchDB osint_scans database"""
    try:
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            response = await client.put(
                f"{COUCHDB_URL}/{COUCHDB_DB}/{case_id}",
                json=case_data,
                auth=(COUCHDB_USER, COUCHDB_PASS) if COUCHDB_USER else None
            )

            if response.status_code not in [201, 202]:
                print(f"CouchDB save error: {response.status_code}")
    except Exception as e:
        print(f"CouchDB save error: {e}")

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
    """

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

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Health check"""
    return {
        "service": "Loom OSINT Orchestration Platform",
        "status": "operational",
        "version": "2.0.0"
    }

@app.get("/health")
async def health():
    """Health check with service status"""
    health_status = {
        "api": "ok",
        "ollama": "unknown",
        "postgres": "ok" if pg_pool else "disabled",
        "couchdb": "unknown"
    }

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            if response.status_code == 200:
                health_status["ollama"] = "ok"
    except:
        health_status["ollama"] = "error"

    # Check CouchDB
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            response = await client.get(
                f"{COUCHDB_URL}/{COUCHDB_DB}",
                auth=(COUCHDB_USER, COUCHDB_PASS) if COUCHDB_USER else None
            )
            if response.status_code == 200:
                health_status["couchdb"] = "ok"
    except:
        health_status["couchdb"] = "error"

    return health_status

@app.get("/tools", dependencies=[Depends(verify_api_key)])
async def list_tools():
    """List all available OSINT tools and their status"""
    return {
        "tools": tool_registry.get_all_tools_status()
    }

@app.post("/cases", response_model=PipelineStatus, dependencies=[Depends(verify_api_key)])
async def create_case(case_create: CaseCreate):
    """Create a new case and run the OSINT orchestration pipeline"""

    case_id = str(uuid.uuid4())[:8]

    try:
        await run_osint_pipeline(case_id, case_create)

        tools_completed = []
        tools_failed = []

        case_metadata = await load_case_metadata(case_id)
        for result in case_metadata.get("tool_results", []):
            if result.get("status") == "success":
                tools_completed.append(result.get("tool"))
            else:
                tools_failed.append(result.get("tool"))

        return PipelineStatus(
            case_id=case_id,
            status="completed",
            stage="report_generated",
            tools_completed=tools_completed,
            tools_failed=tools_failed,
            message=f"Pipeline completed: {len(tools_completed)} tools succeeded, {len(tools_failed)} failed",
            report_ready=True
        )

    except Exception as e:
        await log_to_postgres(case_id, "loom", "error", "pipeline_failed", {"error": str(e)})
        return PipelineStatus(
            case_id=case_id,
            status="error",
            stage="failed",
            message=str(e),
            report_ready=False
        )

@app.get("/cases", dependencies=[Depends(verify_api_key)])
async def list_cases():
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
async def get_case(case_id: str):
    """Get case details"""
    metadata = await load_case_metadata(case_id)

    if not metadata:
        raise HTTPException(status_code=404, detail="Case not found")

    return metadata

@app.get("/cases/{case_id}/report", dependencies=[Depends(verify_api_key)])
async def get_report(case_id: str):
    """Get case report"""
    report_file = CASES_DIR / case_id / "report.md"

    if not report_file.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    async with aiofiles.open(report_file, "r") as f:
        report = await f.read()

    return {"case_id": case_id, "report": report}

@app.get("/cases/{case_id}/tools/{tool_name}", dependencies=[Depends(verify_api_key)])
async def get_tool_results(case_id: str, tool_name: str):
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8787)
