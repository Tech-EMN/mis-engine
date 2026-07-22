"""
MIS Engine — FastAPI Application
================================
REST API wrapping the MIS extraction pipeline with async task management.

Endpoints:
  GET  /api/v1/health                     — Healthcheck
  POST /api/v1/extract                    — Start async extraction (202 + polling)
  GET  /api/v1/extract/{task_id}/status   — Poll extraction status
  GET  /api/v1/projects                   — List processed projects
  GET  /api/v1/projects/{project_id}      — Project detail

Author: Daedalus (AG01) | SDS Phase 4 — Sprint 1 | 2026-07-15
"""
import json
import logging
import os
import sys
import time
import uuid
import threading
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Add project root to path for pipeline import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import MISPipeline, ExtractionResult
from db import store  # dual-mode: Supabase + in-memory

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv(override=False)  # no-op if .env missing (container-friendly)

# Logging: JSON structured
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger("mis-engine")

# Secrets
SECRETS_PATH = os.environ.get(
    "MIS_SECRETS_PATH",
    "/root/.openclaw/secrets/openclaw-secrets.json"
)

def load_secrets() -> dict:
    try:
        with open(SECRETS_PATH) as f:
            return json.load(f)
    except Exception:
        logger.warning("Secrets file not found at %s", SECRETS_PATH)
        return {}

# ============================================================
# TASK STORE (dual-mode: Supabase + in-memory fallback via db.py)
# ============================================================

# store is imported from db module

# ============================================================
# PIPELINE INITIALIZATION
# ============================================================

pipeline: Optional[MISPipeline] = None

def get_pipeline() -> MISPipeline:
    global pipeline
    if pipeline is None:
        secrets = load_secrets()
        pipeline = MISPipeline(secrets)
        logger.info("Pipeline initialized", extra={"ezdxf": "ok"})
    return pipeline

# ============================================================
# PYDANTIC MODELS
# ============================================================

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    pipeline: str = "draft-c-v2"
    dependencies: dict = Field(default_factory=dict)
    uptime_seconds: float = 0.0

class ExtractAccepted(BaseModel):
    task_id: str
    status: str = "pending"
    status_url: str

class ExtractStatus(BaseModel):
    task_id: str
    status: str
    progress_pct: int = 0
    source_type: Optional[str] = None
    project_name: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None

class ProjectSummary(BaseModel):
    id: str
    name: str
    source_type: Optional[str] = None
    status: str
    total_rooms: Optional[int] = None
    created_at: str

class ProjectList(BaseModel):
    total: int
    limit: int
    offset: int
    projects: list

class ErrorResponse(BaseModel):
    error: str
    detail: str
    code: Optional[str] = None

# ============================================================
# LIFESPAN
# ============================================================

start_time = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MIS Engine starting", extra={"version": "1.0.0"})
    get_pipeline()  # pre-warm
    yield
    logger.info("MIS Engine shutting down")

# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="MIS Engine API",
    description="Pipeline de extração e análise de projetos arquitetônicos com IA",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow front-end from GitHub Pages + Netlify + localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tech-emn.github.io",
        "https://mis-dashboard.netlify.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/api/v1/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Healthcheck — status do pipeline e dependências."""
    deps = {}
    try:
        import ezdxf
        deps["ezdxf"] = ezdxf.__version__ if hasattr(ezdxf, '__version__') else "installed"
    except ImportError:
        deps["ezdxf"] = "missing"
    
    try:
        import shapely
        deps["shapely"] = shapely.__version__
    except ImportError:
        deps["shapely"] = "missing"
    
    try:
        import anthropic
        deps["anthropic"] = anthropic.__version__ if hasattr(anthropic, '__version__') else "installed"
    except ImportError:
        deps["anthropic"] = "missing"
    
    return HealthResponse(
        status="ok",
        dependencies=deps,
        uptime_seconds=time.time() - start_time,
    )


@app.post(
    "/api/v1/extract",
    response_model=ExtractAccepted,
    status_code=202,
    tags=["Extraction"],
)
async def extract_project(
    file: UploadFile = File(...),
    project_name: Optional[str] = Form(None),
):
    """
    Iniciar extração assíncrona de projeto arquitetônico.
    
    Recebe arquivo (PDF/DXF/DWG), cria task assíncrona, retorna 202 + task_id.
    Poll /api/v1/extract/{task_id}/status para acompanhar progresso.
    """
    # Validate file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ('.pdf', '.dxf', '.dwg'):
        raise HTTPException(
            status_code=415,
            detail=f"Formato não suportado: {ext}. Use PDF, DXF ou DWG."
        )
    
    # Create task
    task = store.create_task(file.filename, project_name)
    task_id = task["task_id"]
    
    # Save uploaded file temporarily
    tmp_path = f"/tmp/mis-upload-{task_id}{ext}"
    try:
        content = await file.read()
        with open(tmp_path, 'wb') as f:
            f.write(content)
        
        logger.info("File received", extra={
            "task_id": task_id,
            "file_name": file.filename,
            "size_bytes": len(content),
        })
    except Exception as e:
        store.update_task(task_id, status="failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")
    
    # Launch async extraction in background thread
    store.update_task(task_id, status="processing", progress_pct=10)
    thread = threading.Thread(
        target=_run_extraction,
        args=(task_id, tmp_path, ext),
        daemon=True,
    )
    thread.start()
    
    return ExtractAccepted(
        task_id=task_id,
        status_url=f"/api/v1/extract/{task_id}/status",
    )


def _run_extraction(task_id: str, file_path: str, ext: str):
    """Background extraction worker."""
    try:
        pip = get_pipeline()
        result: ExtractionResult = pip.process(file_path)
        
        result_dict = json.loads(pip.to_json(result))
        
        store.update_task(
            task_id,
            status="done",
            progress_pct=100,
            source_type=result.source_type.value,
            total_rooms=len(result.rooms),
            result=result_dict,
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        logger.info("Extraction complete", extra={
            "task_id": task_id,
            "source_type": result.source_type.value,
            "rooms": len(result.rooms),
            "elapsed_ms": result.elapsed_ms,
        })
    except Exception as e:
        logger.error("Extraction failed", extra={"task_id": task_id, "error": str(e)})
        store.update_task(
            task_id,
            status="failed",
            progress_pct=0,
            error=str(e),
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
    finally:
        # Clean up temp file
        try:
            os.unlink(file_path)
        except OSError:
            pass


@app.get(
    "/api/v1/extract/{task_id}/status",
    response_model=ExtractStatus,
    tags=["Extraction"],
)
async def get_extraction_status(task_id: str):
    """Consultar status de extração por task_id (polling)."""
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    return ExtractStatus(
        task_id=task["task_id"],
        status=task["status"],
        progress_pct=task["progress_pct"],
        source_type=task.get("source_type"),
        project_name=task.get("name", task.get("filename", "unknown")),
        result=task.get("result"),
        error=task.get("error"),
    )


@app.get(
    "/api/v1/projects",
    response_model=ProjectList,
    tags=["Projects"],
)
async def list_projects(
    status: Optional[str] = Query(None, enum=["pending", "processing", "done", "failed"]),
    source_type: Optional[str] = Query(None, enum=["pdf", "dxf", "dwg"]),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Listar projetos processados (Supabase when available, in-memory fallback).
    """
    result = store.list_tasks(status=status, limit=limit, offset=offset)
    return ProjectList(
        total=result["total"],
        limit=result["limit"],
        offset=result["offset"],
        projects=result["projects"],
    )


@app.get(
    "/api/v1/projects/{project_id}",
    tags=["Projects"],
)
async def get_project(project_id: str):
    """Detalhes completos de um projeto (Supabase ou in-memory)."""
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return project


# ============================================================
# GLOBAL ERROR HANDLERS
# ============================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    logger.warning("HTTP exception", extra={
        "status_code": exc.status_code,
        "detail": exc.detail,
        "path": str(request.url.path),
    })
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "detail": str(exc.detail),
            "code": f"HTTP_{exc.status_code}",
        },
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc: Exception):
    logger.error("Unhandled exception", extra={
        "error": str(exc),
        "path": str(request.url.path),
    }, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "code": "INTERNAL_ERROR",
        },
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting MIS Engine on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
