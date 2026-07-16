"""
MIS Engine — Supabase Integration
==================================
Dual-mode storage: Supabase (when tables exist) with in-memory fallback.

Requires migration 001_schema.sql to be executed first via Supabase Dashboard.
Once tables exist, all operations persist to Supabase automatically.
"""
import json
import os
import logging
import time
import threading
import uuid
from typing import Optional, Dict, List
from dataclasses import dataclass, field, asdict

import requests

logger = logging.getLogger("mis-engine.db")

# ============================================================
# CONFIG
# ============================================================

SECRETS_PATH = os.environ.get(
    "MIS_SECRETS_PATH",
    "/root/.openclaw/secrets/openclaw-secrets.json",
)

def _load_config():
    # Tenta variáveis de ambiente primeiro (container Railway)
    url = os.environ.get("SUPABASE_LUG_URL")
    key = os.environ.get("SUPABASE_LUG_SECRET_KEY")
    if url and key:
        logger.info("Supabase config loaded from environment variables")
        return {"url": url, "key": key}

    # Fallback: arquivo de secrets (dev local)
    try:
        with open(SECRETS_PATH) as f:
            s = json.load(f)
        return {
            "url": s["SUPABASE_LUG_URL"],
            "key": s["SUPABASE_LUG_SECRET_KEY"],
        }
    except Exception:
        logger.warning("Supabase config not found — in-memory only mode")
        return None

# ============================================================
# IN-MEMORY STORE (fallback)
# ============================================================

class InMemoryStore:
    """Thread-safe in-memory task/project store."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: Dict[str, dict] = {}
    
    def create_task(self, filename: str, project_name: str = None) -> dict:
        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "task_id": task_id,
            "name": project_name or filename,
            "filename": filename,
            "source_type": None,
            "status": "pending",
            "progress_pct": 0,
            "total_rooms": 0,
            "result": None,
            "error": None,
            "warnings": [],
            "fragilities": [],
            "elapsed_ms": 0,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "completed_at": None,
        }
        with self._lock:
            self._tasks[task_id] = task
        return task
    
    def get_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            return self._tasks.get(task_id)
    
    def update_task(self, task_id: str, **kwargs):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(kwargs)
    
    def list_tasks(self, status: str = None, source_type: str = None,
                   limit: int = 20, offset: int = 0) -> List[dict]:
        with self._lock:
            tasks = list(self._tasks.values())
            if status:
                tasks = [t for t in tasks if t["status"] == status]
            if source_type:
                tasks = [t for t in tasks if t.get("source_type") == source_type]
            tasks.sort(key=lambda t: t["created_at"], reverse=True)
            return tasks[offset:offset + limit]
    
    def count_tasks(self, status: str = None, source_type: str = None) -> int:
        with self._lock:
            tasks = list(self._tasks.values())
            if status:
                tasks = [t for t in tasks if t["status"] == status]
            if source_type:
                tasks = [t for t in tasks if t.get("source_type") == source_type]
            return len(tasks)


# ============================================================
# SUPABASE STORE
# ============================================================

class SupabaseStore:
    """Supabase-backed project store via REST API."""
    
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        self._available = None
    
    @property
    def available(self) -> bool:
        """Check if Supabase tables exist (cached)."""
        if self._available is None:
            try:
                r = requests.get(
                    f"{self.url}/rest/v1/mis_projects?limit=0",
                    headers=self.headers,
                    timeout=5,
                )
                self._available = r.status_code == 200
                if not self._available:
                    logger.info("Supabase tables not found — using in-memory mode")
            except Exception:
                self._available = False
        return self._available
    
    def create_project(self, task: dict) -> Optional[dict]:
        """Insert project into Supabase."""
        if not self.available:
            return None
        try:
            project_data = {
                "name": task["name"],
                "source_type": task.get("source_type"),
                "status": task["status"],
                "total_rooms": task.get("total_rooms", 0),
                "error": task.get("error"),
                "warnings": task.get("warnings", []),
                "fragilities": task.get("fragilities", []),
                "elapsed_ms": task.get("elapsed_ms", 0),
                "metadata": {"task_id": task["task_id"], "filename": task.get("filename", "")},
            }
            headers = {**self.headers, "Prefer": "return=representation"}
            r = requests.post(
                f"{self.url}/rest/v1/mis_projects",
                headers=headers,
                json=project_data,
                timeout=10,
            )
            if r.status_code == 201:
                return r.json()[0]
            logger.warning("Supabase insert project failed: %s", r.text[:200])
        except Exception as e:
            logger.warning("Supabase error (create_project): %s", e)
        return None
    
    def update_project(self, supabase_id: str, **kwargs) -> bool:
        """Update project in Supabase."""
        if not self.available:
            return False
        try:
            r = requests.patch(
                f"{self.url}/rest/v1/mis_projects?id=eq.{supabase_id}",
                headers=self.headers,
                json=kwargs,
                timeout=10,
            )
            return r.status_code == 204 or r.status_code == 200
        except Exception as e:
            logger.warning("Supabase error (update_project): %s", e)
        return False
    
    def save_result(self, supabase_project_id: str, task: dict) -> bool:
        """Save extraction result: update project + insert rooms + insert extraction log."""
        if not self.available:
            return False
        
        result = task.get("result", {})
        rooms = result.get("rooms", []) if isinstance(result, dict) else []
        
        # Update project status
        self.update_project(supabase_project_id,
            status=task["status"],
            total_rooms=len(rooms),
            error=task.get("error"),
            warnings=task.get("warnings", []),
            fragilities=result.get("fragilities", []) if isinstance(result, dict) else [],
            elapsed_ms=result.get("elapsed_ms", 0) if isinstance(result, dict) else 0,
            completed_at=task.get("completed_at"),
        )
        
        # Insert rooms
        for room in rooms:
            try:
                room_data = {
                    "project_id": supabase_project_id,
                    "name": room.get("name", "Ambiente"),
                    "area_m2": room.get("area_m2", 0),
                    "perimeter_m": room.get("perimeter_m", 0),
                    "width_m": room.get("width_m", 0),
                    "length_m": room.get("length_m", 0),
                    "shape": room.get("shape", "rectangle"),
                    "confidence_geometry": room.get("confidence", {}).get("geometry", 1.0) if isinstance(room.get("confidence"), dict) else 1.0,
                    "confidence_name": room.get("confidence", {}).get("name", 0.5) if isinstance(room.get("confidence"), dict) else 0.5,
                    "needs_human_review": room.get("needs_human_review", False),
                    "review_reason": room.get("review_reason"),
                    "faces": room.get("faces", []),
                }
                requests.post(
                    f"{self.url}/rest/v1/mis_rooms",
                    headers=self.headers,
                    json=room_data,
                    timeout=10,
                )
            except Exception as e:
                logger.warning("Supabase room insert error: %s", e)
        
        # Insert extraction log
        try:
            extraction_data = {
                "project_id": supabase_project_id,
                "task_id": task["task_id"],
                "filename": task.get("filename", ""),
                "result_json": result if isinstance(result, dict) else {},
            }
            requests.post(
                f"{self.url}/rest/v1/mis_extractions",
                headers=self.headers,
                json=extraction_data,
                timeout=10,
            )
        except Exception as e:
            logger.warning("Supabase extraction insert error: %s", e)
        
        return True
    
    def list_projects(self, status: str = None, limit: int = 20, offset: int = 0) -> dict:
        """List projects from Supabase with pagination."""
        if not self.available:
            return {"total": 0, "projects": []}
        
        try:
            params = [
                ("order", "created_at.desc"),
                ("limit", str(limit)),
                ("offset", str(offset)),
            ]
            if status:
                params.append(("status", f"eq.{status}"))
            
            query = "&".join(f"{k}={v}" for k, v in params)
            r = requests.get(
                f"{self.url}/rest/v1/mis_projects?{query}",
                headers={**self.headers, "Prefer": "count=exact"},
                timeout=10,
            )
            if r.status_code == 200:
                total = int(r.headers.get("content-range", "0/0").split("/")[-1])
                projects = []
                for p in r.json():
                    projects.append({
                        "id": p["id"],
                        "name": p["name"],
                        "source_type": p.get("source_type"),
                        "status": p["status"],
                        "total_rooms": p.get("total_rooms"),
                        "created_at": p["created_at"],
                    })
                return {"total": total, "projects": projects}
        except Exception as e:
            logger.warning("Supabase error (list_projects): %s", e)
        return {"total": 0, "projects": []}
    
    def get_project(self, project_id: str) -> Optional[dict]:
        """Get project with rooms from Supabase."""
        if not self.available:
            return None
        
        try:
            # Get project
            r = requests.get(
                f"{self.url}/rest/v1/mis_projects?id=eq.{project_id}&limit=1",
                headers=self.headers,
                timeout=10,
            )
            if r.status_code != 200 or not r.json():
                return None
            project = r.json()[0]
            
            # Get rooms
            r2 = requests.get(
                f"{self.url}/rest/v1/mis_rooms?project_id=eq.{project_id}&order=created_at.asc",
                headers=self.headers,
                timeout=10,
            )
            rooms = r2.json() if r2.status_code == 200 else []
            
            return {
                "id": project["id"],
                "name": project["name"],
                "source_type": project.get("source_type"),
                "status": project["status"],
                "created_at": project["created_at"],
                "result": {
                    "total_rooms": len(rooms),
                    "rooms": rooms,
                    "fragilities": project.get("fragilities", []),
                    "warnings": project.get("warnings", []),
                    "elapsed_ms": project.get("elapsed_ms", 0),
                },
                "error": project.get("error"),
            }
        except Exception as e:
            logger.warning("Supabase error (get_project): %s", e)
        return None


# ============================================================
# DUAL-MODE STORE
# ============================================================

class Store:
    """Dual-mode store: Supabase (when available) with in-memory fallback."""
    
    def __init__(self):
        config = _load_config()
        self.memory = InMemoryStore()
        self.supabase = SupabaseStore(config["url"], config["key"]) if config else None
        self._supabase_ids: Dict[str, str] = {}  # task_id → supabase_project_id
    
    @property
    def using_supabase(self) -> bool:
        return self.supabase is not None and self.supabase.available
    
    def create_task(self, filename: str, project_name: str = None) -> dict:
        task = self.memory.create_task(filename, project_name)
        
        # Also try Supabase
        if self.supabase:
            supabase_project = self.supabase.create_project(task)
            if supabase_project:
                self._supabase_ids[task["task_id"]] = supabase_project["id"]
                task["_supabase_id"] = supabase_project["id"]
                logger.info("Task persisted to Supabase: %s", supabase_project["id"])
        
        return task
    
    def get_task(self, task_id: str) -> Optional[dict]:
        return self.memory.get_task(task_id)
    
    def update_task(self, task_id: str, **kwargs):
        self.memory.update_task(task_id, **kwargs)
        
        # If extraction complete, persist to Supabase
        if kwargs.get("status") in ("done", "failed") and self.supabase:
            task = self.memory.get_task(task_id)
            if task:
                supabase_id = self._supabase_ids.get(task_id)
                if supabase_id:
                    self.supabase.save_result(supabase_id, task)
                else:
                    # Create in Supabase if not already created
                    supabase_project = self.supabase.create_project(task)
                    if supabase_project:
                        self._supabase_ids[task_id] = supabase_project["id"]
                        self.supabase.save_result(supabase_project["id"], task)
    
    def list_tasks(self, status: str = None, source_type: str = None,
                   limit: int = 20, offset: int = 0) -> dict:
        if self.using_supabase:
            result = self.supabase.list_projects(status=status, limit=limit, offset=offset)
            if result["total"] > 0:
                return {
                    "total": result["total"],
                    "limit": limit,
                    "offset": offset,
                    "projects": result["projects"],
                }
        
        # Fallback to in-memory
        tasks = self.memory.list_tasks(status, source_type, limit, offset)
        total = self.memory.count_tasks(status, source_type)
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "projects": tasks,
        }
    
    def get_project(self, project_id: str) -> Optional[dict]:
        if self.using_supabase:
            project = self.supabase.get_project(project_id)
            if project:
                return project
        
        # Fallback to in-memory
        task = self.memory.get_task(project_id)
        if task:
            return {
                "id": task["task_id"],
                "name": task["name"],
                "source_type": task.get("source_type"),
                "status": task["status"],
                "created_at": task["created_at"],
                "result": task.get("result"),
                "error": task.get("error"),
            }
        return None


# Singleton
store = Store()
