"""
Loom MVP - OSINT Console Backend
Local-first OSINT pipeline powered by Ollama and SearXNG
"""

import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import aiofiles

# ============================================================================
# Configuration
# ============================================================================

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://pi-forge.nexus.lan:11434")
SEARXNG_URL = os.getenv("SEARXNG_URL", "https://searxng.lan")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
CASES_DIR = DATA_DIR / "cases"
API_KEY = os.getenv("OSINT_API_KEY", "")

# Ensure data directories exist
CASES_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Loom OSINT API",
    description="Local-first OSINT console powered by Ollama",
    version="1.0.0"
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

class CaseCreate(BaseModel):
    """Request to create a new case"""
    title: str = Field(..., description="Case title/subject")
    description: Optional[str] = Field(None, description="Case description")
    initial_query: str = Field(..., description="Initial research query")

class QueryPlan(BaseModel):
    """Ollama-generated query plan"""
    queries: List[str] = Field(default_factory=list)
    reasoning: Optional[str] = None

class SearchResult(BaseModel):
    """Individual search result"""
    title: str
    url: str
    content: str
    engine: Optional[str] = None

class PipelineStatus(BaseModel):
    """Pipeline execution status"""
    case_id: str
    status: str
    stage: str
    message: Optional[str] = None
    report_ready: bool = False

class CaseInfo(BaseModel):
    """Case metadata"""
    case_id: str
    title: str
    description: Optional[str]
    created_at: str
    status: str

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

async def generate_query_plan(case_description: str, initial_query: str) -> QueryPlan:
    """Generate search query plan using Ollama"""

    system_prompt = """You are an OSINT research assistant. Given a research objective, generate a strategic list of search queries to gather comprehensive information.

Output ONLY valid JSON in this exact format:
{
  "reasoning": "brief explanation of the search strategy",
  "queries": ["query 1", "query 2", "query 3"]
}

Generate 3-5 specific, targeted search queries."""

    user_prompt = f"""Research Objective: {case_description}

Initial Query: {initial_query}

Generate a strategic search plan with specific queries."""

    try:
        response = await call_ollama(user_prompt, system=system_prompt, json_mode=True)
        plan_data = json.loads(response)
        return QueryPlan(**plan_data)

    except json.JSONDecodeError:
        # Fallback: use the initial query
        return QueryPlan(
            queries=[initial_query],
            reasoning="Using initial query as fallback"
        )

async def synthesize_report(case_data: Dict[str, Any], search_results: List[Dict]) -> str:
    """Synthesize search results into a markdown report using Ollama"""

    system_prompt = """You are an OSINT analyst. Synthesize the provided search results into a comprehensive, well-structured intelligence report.

Format your report in markdown with:
- Executive Summary
- Key Findings (organized by theme)
- Detailed Analysis
- Sources

Be factual, cite sources, and highlight information gaps."""

    # Prepare search results summary
    results_text = "\n\n".join([
        f"### Result {i+1}\n**Title:** {r.get('title', 'N/A')}\n**URL:** {r.get('url', 'N/A')}\n**Content:** {r.get('content', 'N/A')[:500]}..."
        for i, r in enumerate(search_results[:20])  # Limit to top 20 results
    ])

    user_prompt = f"""Case: {case_data.get('title')}
Description: {case_data.get('description', 'N/A')}

Search Results:
{results_text}

Generate a comprehensive OSINT report."""

    report = await call_ollama(user_prompt, system=system_prompt)
    return report

# ============================================================================
# SearXNG Integration
# ============================================================================

async def search_searxng(query: str, num_results: int = 10) -> List[SearchResult]:
    """Search using SearXNG"""
    try:
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            params = {
                "q": query,
                "format": "json",
                "pageno": 1
            }

            response = await client.get(
                f"{SEARXNG_URL}/search",
                params=params
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("results", [])[:num_results]:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    engine=item.get("engine")
                ))

            return results

    except Exception as e:
        # Return empty results on error (SearXNG might not be available)
        print(f"SearXNG error: {e}")
        return []

# ============================================================================
# Case Management
# ============================================================================

def create_case_directory(case_id: str) -> Path:
    """Create case directory structure"""
    case_dir = CASES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "raw").mkdir(exist_ok=True)
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

async def save_search_results(case_id: str, results: List[SearchResult], query_idx: int):
    """Save raw search results"""
    case_dir = CASES_DIR / case_id
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"searx_bundle_{query_idx}_{timestamp}.json"

    raw_file = case_dir / "raw" / filename

    results_data = [r.dict() for r in results]

    async with aiofiles.open(raw_file, "w") as f:
        await f.write(json.dumps(results_data, indent=2))

async def save_report(case_id: str, report: str):
    """Save final markdown report"""
    case_dir = CASES_DIR / case_id
    report_file = case_dir / "report.md"

    async with aiofiles.open(report_file, "w") as f:
        await f.write(report)

# ============================================================================
# Pipeline Orchestration
# ============================================================================

async def run_osint_pipeline(case_id: str, case_create: CaseCreate) -> Dict[str, Any]:
    """
    Execute the full OSINT pipeline:
    1. Create case
    2. Generate query plan (Ollama)
    3. Execute searches (SearXNG)
    4. Synthesize report (Ollama)
    5. Save results
    """

    # 1. Create case structure
    create_case_directory(case_id)

    case_metadata = {
        "case_id": case_id,
        "title": case_create.title,
        "description": case_create.description,
        "initial_query": case_create.initial_query,
        "created_at": datetime.utcnow().isoformat(),
        "status": "processing"
    }

    await save_case_metadata(case_id, case_metadata)

    # 2. Generate query plan
    query_plan = await generate_query_plan(
        case_create.description or case_create.title,
        case_create.initial_query
    )

    case_metadata["query_plan"] = query_plan.dict()
    await save_case_metadata(case_id, case_metadata)

    # 3. Execute searches
    all_results = []
    for idx, query in enumerate(query_plan.queries):
        results = await search_searxng(query, num_results=15)
        all_results.extend(results)
        await save_search_results(case_id, results, idx)

    case_metadata["total_results"] = len(all_results)
    case_metadata["status"] = "synthesizing"
    await save_case_metadata(case_id, case_metadata)

    # 4. Synthesize report
    report = await synthesize_report(
        case_metadata,
        [r.dict() for r in all_results]
    )

    await save_report(case_id, report)

    # 5. Mark complete
    case_metadata["status"] = "completed"
    case_metadata["completed_at"] = datetime.utcnow().isoformat()
    await save_case_metadata(case_id, case_metadata)

    return case_metadata

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Health check"""
    return {
        "service": "Loom OSINT API",
        "status": "operational",
        "version": "1.0.0"
    }

@app.get("/health")
async def health():
    """Health check with service status"""
    health_status = {
        "api": "ok",
        "ollama": "unknown",
        "searxng": "unknown"
    }

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            if response.status_code == 200:
                health_status["ollama"] = "ok"
    except:
        health_status["ollama"] = "error"

    # Check SearXNG
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            response = await client.get(SEARXNG_URL)
            if response.status_code == 200:
                health_status["searxng"] = "ok"
    except:
        health_status["searxng"] = "error"

    return health_status

@app.post("/cases", response_model=PipelineStatus, dependencies=[Depends(verify_api_key)])
async def create_case(case_create: CaseCreate):
    """Create a new case and run the OSINT pipeline"""

    case_id = str(uuid.uuid4())[:8]

    try:
        await run_osint_pipeline(case_id, case_create)

        return PipelineStatus(
            case_id=case_id,
            status="completed",
            stage="report_generated",
            message="Pipeline completed successfully",
            report_ready=True
        )

    except Exception as e:
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

@app.get("/config")
async def get_config():
    """Get public configuration (for UI)"""
    return {
        "ollama_url": OLLAMA_URL,
        "ollama_model": OLLAMA_MODEL,
        "searxng_url": SEARXNG_URL,
        "api_key_required": bool(API_KEY)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8787)
