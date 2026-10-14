"""Single-process pilot API with a bounded queue and isolated GDAL workers."""
from __future__ import annotations
import json
import hmac
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import List, Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from cloud_session import COOKIE, session_id, owner_id, browser_origin

ROOT = Path(os.environ.get("QC_JOB_ROOT", str(Path(__file__).parent / "qc_jobs"))).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
WORKER = Path(__file__).with_name("cloud_gdb_worker.py")
WORKER_PYTHON = os.environ.get("QC_WORKER_PYTHON", sys.executable)
API_KEY = os.environ.get("QC_API_KEY", "")
MAX_UPLOAD = int(os.environ.get("QC_MAX_UPLOAD_MB", "128")) * 1024 * 1024
MAX_UNPACKED = int(os.environ.get("QC_MAX_UNPACKED_MB", "1024")) * 1024 * 1024
TIMEOUT = int(os.environ.get("QC_JOB_TIMEOUT_SECONDS", "1800"))
QUEUE_LIMIT = int(os.environ.get("QC_MAX_QUEUED_JOBS", "10"))
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gdb-queue")
ACTIVE = set()
LOCK = threading.RLock()
router = APIRouter(prefix="/gdb", tags=["Cloud GDB QC"])


def authorize(request: Request):
    if not API_KEY:
        raise HTTPException(503, "QC_API_KEY must be configured on the server before use.")
    origin = request.headers.get("Origin")
    allowed = {x.strip() for x in os.environ.get("QC_ALLOWED_ORIGINS", "").split(",") if x.strip()}
    allowed.add(browser_origin(request))
    if origin and origin not in allowed and "*" not in allowed:
        raise HTTPException(403, "This frontend origin is not allowed by the QC service.")
    key = request.headers.get("X-GDB-Key", "")
    if key:
        if hmac.compare_digest(key.encode("utf-8"), API_KEY.encode("utf-8")):
            return "api-key"
        raise HTTPException(401, "Invalid QC API key.")
    sid = session_id(request.cookies.get(COOKIE, ""))
    if sid is None:
        raise HTTPException(401, "Open or reload the cloud portal to start your browser session.")
    # Browser sessions are same-origin even if legacy API-key origins are allowed.
    if origin and origin != browser_origin(request):
        raise HTTPException(403, "Open the portal and QC service at the same cloud address.")
    return owner_id(sid)


def owned_job(job_id, owner):
    path = job_dir(job_id)
    saved = (path / "owner.json")
    expected = read_json(saved).get("owner") if saved.exists() else None
    if owner != "api-key" and owner != expected:
        raise HTTPException(404, "Job not found or expired for this browser session.")
    return path


def job_dir(job_id):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(400, "Invalid job identifier.")
    path = ROOT / job_id
    if not path.is_dir():
        raise HTTPException(404, "Job not found or expired.")
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def create_job(action, owner):
    # Expire completed uploads/results after 24 hours. Never delete running tasks.
    with LOCK:
        for path in ROOT.iterdir():
            if not path.is_dir() or not re.fullmatch(r"[a-f0-9]{32}", path.name) or path.name in ACTIVE:
                continue
            state_file = path / "status.json"
            if state_file.exists() and time.time() - state_file.stat().st_mtime > 86400:
                state = read_json(state_file)
                if state.get("state") not in {"running", "queued"}:
                    shutil.rmtree(path, ignore_errors=True)
        if len(ACTIVE) >= QUEUE_LIMIT:
            raise HTTPException(429, "The GDB queue is full. Retry after a job finishes.")
        job_id = uuid.uuid4().hex
        path = ROOT / job_id
        path.mkdir()
        ACTIVE.add(job_id)
        write_json(path / "owner.json", {"owner": owner})
        write_json(path / "status.json", {"job_id": job_id, "action": action, "state": "preparing", "progress": 0, "message": "Receiving files"})
    return job_id, path


def queue_job(job_id, task):
    path = job_dir(job_id)
    write_json(path / "task.json", task)
    write_json(path / "status.json", {"job_id": job_id, "action": task["action"], "state": "queued", "progress": 0, "message": "Waiting for the GDAL worker"})
    POOL.submit(run_job, job_id)
    return {"job_id": job_id}


def run_job(job_id):
    path = job_dir(job_id)
    task = read_json(path / "task.json")
    base = {"job_id": job_id, "action": task["action"]}
    write_json(path / "status.json", {**base, "state": "running", "progress": 1, "message": "GDAL processing started"})
    try:
        with (path / "worker.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run([WORKER_PYTHON, str(WORKER), str(path / "task.json")], stdout=log, stderr=subprocess.STDOUT,
                                       cwd=str(WORKER.parent), timeout=TIMEOUT, check=False)
        if completed.returncode:
            error_file = path / "worker_error.json"
            error = read_json(error_file)["error"] if error_file.exists() else "GDAL worker failed. Check the server's job log."
            raise RuntimeError(error)
        result = read_json(path / "result.json")
        write_json(path / "status.json", {**base, "state": "completed_with_warnings" if result.get("has_warnings") else "completed", "progress": 100, "message": "Finished", "result": result})
    except Exception as exc:
        write_json(path / "status.json", {**base, "state": "failed", "progress": 0, "message": str(exc)})
    finally:
        with LOCK:
            ACTIVE.discard(job_id)


def restore_job_states():
    # A restart loses in-memory queue ownership. Make abandoned jobs explicit.
    for path in ROOT.glob("*/status.json"):
        try:
            state = read_json(path)
            if state.get("state") in {"preparing", "queued", "running"}:
                state.update(state="failed", progress=0, message="Service restarted before this job completed. Upload and run it again.")
                write_json(path, state)
        except (ValueError, OSError):
            continue


def extract_gdb(archive, destination):
    """Bounded ZIP extraction with Windows path, symlink and traversal validation."""
    destination = Path(destination)
    with zipfile.ZipFile(archive) as zipped:
        members = []
        roots = set()
        total = 0
        seen = set()
        for item in zipped.infolist():
            raw = item.filename.replace("\\", "/")
            parts = PurePosixPath(raw).parts
            if not parts:
                continue
            if raw.startswith("/") or any(p in {"..", "."} or ":" in p or p.endswith((".", " ")) for p in parts):
                raise ValueError("Unsafe ZIP path: " + raw)
            if any(re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p, re.I) for p in parts):
                raise ValueError("ZIP contains a reserved Windows filename.")
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("ZIP contains a symbolic link.")
            if parts[0] == "__MACOSX":
                continue
            gdb_index = next((i for i, p in enumerate(parts) if p.lower().endswith(".gdb")), None)
            if gdb_index is None:
                continue
            root = parts[:gdb_index + 1]
            roots.add(root)
            rel = parts[gdb_index:]
            normalized = "/".join(rel).lower()
            if normalized in seen:
                raise ValueError("ZIP contains colliding filenames.")
            seen.add(normalized)
            total += item.file_size
            if total > MAX_UNPACKED or len(members) >= 100000:
                raise ValueError("Unpacked GDB exceeds the configured size or file-count limit.")
            members.append((item, rel))
        if len(roots) != 1:
            raise ValueError("Upload a ZIP containing exactly one .gdb folder, including its internal files.")
        for item, rel in members:
            target = destination.joinpath(*rel)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif not target.name.lower().endswith(".lock"):
                target.parent.mkdir(parents=True, exist_ok=True)
                # Enforce the byte limit even if a ZIP entry reports a false size.
                copied = 0
                with zipped.open(item) as source, target.open("wb") as output:
                    while True:
                        block = source.read(1024 * 1024)
                        if not block:
                            break
                        copied += len(block)
                        if copied > item.file_size or copied > MAX_UNPACKED:
                            raise ValueError("ZIP entry exceeds its declared size.")
                        output.write(block)
        name = next(iter(roots))[-1]
        gdb = destination / name
        if not any(p.is_file() for p in gdb.iterdir()):
            raise ValueError("The .gdb folder is empty.")
        return gdb


async def receive_upload(file, destination):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "ZIP the complete .gdb folder before uploading.")
    path = Path(destination) / "upload.zip"
    size = 0
    try:
        with path.open("wb") as stream:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise ValueError("Upload exceeds " + str(MAX_UPLOAD // 1024 // 1024) + " MB.")
                stream.write(chunk)
        return extract_gdb(path, Path(destination) / "uploaded")
    except (ValueError, zipfile.BadZipFile, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        await file.close()
        path.unlink(missing_ok=True)


def upload_reference(upload_id, owner):
    path = owned_job(upload_id, owner)
    state = read_json(path / "status.json")
    if state.get("action") != "inspect" or state.get("state") != "completed":
        raise HTTPException(400, "Load and inspect this GDB successfully before processing.")
    return read_json(path / "task.json")["gdb"], state["result"]["classes"]


def copy_upload(upload_id, destination, owner):
    gdb, _ = upload_reference(upload_id, owner)
    destination = Path(destination) / Path(gdb).name
    shutil.copytree(gdb, destination, ignore=shutil.ignore_patterns("*.lock"))
    return str(destination)


class QCRequest(BaseModel):
    input_upload_id: str
    schema_upload_id: str
    short_limit_m: float = Field(default=2.0, gt=0, le=100000)
    selected: Optional[List[str]] = Field(default=None, min_length=1, max_length=1000)


@router.get("/health", dependencies=[Depends(authorize)])
def health():
    from cloud_gdb_worker import engine_health
    return {**engine_health(), "max_upload_mb": MAX_UPLOAD // 1024 // 1024}


@router.post("/inspect", dependencies=[Depends(authorize)])
async def inspect(file: UploadFile = File(...), owner: str = Depends(authorize)):
    job_id, path = create_job("inspect", owner)
    try:
        gdb = await receive_upload(file, path)
        return queue_job(job_id, {"action": "inspect", "gdb": str(gdb)})
    except Exception as exc:
        with LOCK:
            ACTIVE.discard(job_id)
        write_json(path / "status.json", {"job_id": job_id, "action": "inspect", "state": "failed", "message": str(exc), "progress": 0})
        raise


@router.post("/qc", dependencies=[Depends(authorize)])
def submit_qc(request: QCRequest, owner: str = Depends(authorize)):
    _, classes = upload_reference(request.input_upload_id, owner)
    upload_reference(request.schema_upload_id, owner)
    if request.selected and any(p not in {r["path"] for r in classes} for p in request.selected):
        raise HTTPException(400, "QC selections must reference inspected feature classes.")
    job_id, path = create_job("qc", owner)
    try:
        with LOCK:
            source = copy_upload(request.input_upload_id, path / "input", owner)
            schema = copy_upload(request.schema_upload_id, path / "schema", owner)
        return queue_job(job_id, {"action": "qc", "input_gdb": source, "schema_gdb": schema,
                                  "short_limit_m": request.short_limit_m, "selected": request.selected})
    except Exception:
        with LOCK:
            ACTIVE.discard(job_id)
        shutil.rmtree(path, ignore_errors=True)
        raise


@router.get("/jobs/{job_id}", dependencies=[Depends(authorize)])
def job_status(job_id: str, owner: str = Depends(authorize)):
    path = owned_job(job_id, owner)
    status = read_json(path / "status.json")
    if status.get("state") == "running" and (path / "worker_status.json").exists():
        status.update(read_json(path / "worker_status.json"))
    return status


@router.get("/jobs/{job_id}/download/{filename}", dependencies=[Depends(authorize)])
def download(job_id: str, filename: str, owner: str = Depends(authorize)):
    path = owned_job(job_id, owner)
    status = read_json(path / "status.json")
    names = {r["name"] for r in status.get("result", {}).get("artifacts", [])}
    if status.get("state") not in {"completed", "completed_with_warnings"} or filename not in names:
        raise HTTPException(404, "Output file is not available.")
    return FileResponse(path / filename, filename=filename)
