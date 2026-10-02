import hmac
import os
import shutil
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

from .extract import SUPPORTED
from .parser import parse_resume
from .schema import Resume

load_dotenv()

MAX_BYTES = 10 * 1024 * 1024
JOB_TTL_SECONDS = 3600
WORKERS = int(os.getenv("CV_PARSER_WORKERS", "3"))

app = FastAPI(title="cv_parser")
pool = ThreadPoolExecutor(max_workers=WORKERS)
jobs: dict[str, dict] = {}  # in-memory: results are lost on restart and not shared across instances
jobs_lock = Lock()


class JobStatus(BaseModel):
    job_id: str
    status: str  # queued | processing | done | error
    result: Resume | None = None
    error: str | None = None


def require_token(x_api_key: str | None = Header(None)) -> None:
    expected = os.getenv("CV_PARSER_API_TOKEN")
    if not expected:
        raise HTTPException(500, "CV_PARSER_API_TOKEN is not configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(401, "Invalid or missing X-API-Key")


def _set(job_id: str, **fields) -> None:
    with jobs_lock:
        jobs[job_id].update(fields)


def _purge_expired() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    with jobs_lock:
        for jid in [j for j, v in jobs.items() if v["created"] < cutoff and v["status"] in ("done", "error")]:
            del jobs[jid]


def _run(job_id: str, workdir: Path, path: Path) -> None:
    _set(job_id, status="processing")
    try:
        _set(job_id, status="done", result=parse_resume(path))
    except Exception as e:  # unreadable file or upstream model failure
        _set(job_id, status="error", error=f"Could not parse resume: {e}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/parse", status_code=202, response_model=JobStatus, dependencies=[Depends(require_token)])
def parse(file: UploadFile = File(...)) -> JobStatus:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED:
        raise HTTPException(415, f"Unsupported file type '{ext}'. Use: {', '.join(sorted(SUPPORTED))}")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File larger than 10 MB")

    _purge_expired()
    workdir = Path(tempfile.mkdtemp())
    path = workdir / f"upload{ext}"
    path.write_bytes(data)
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"status": "queued", "result": None, "error": None, "created": time.time()}
    pool.submit(_run, job_id, workdir, path)
    return JobStatus(job_id=job_id, status="queued")


@app.get("/jobs/{job_id}", response_model=JobStatus, dependencies=[Depends(require_token)])
def get_job(job_id: str) -> JobStatus:
    with jobs_lock:
        job = jobs.get(job_id)
        snapshot = dict(job) if job else None
    if snapshot is None:
        raise HTTPException(404, "Job not found (unknown id or expired)")
    return JobStatus(job_id=job_id, status=snapshot["status"], result=snapshot["result"], error=snapshot["error"])
