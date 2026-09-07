"""HTTP service around the CrewAI research pipeline.

A full crew run takes minutes, which is far too long to hold a request open,
so the API uses a job model: POST /research returns a job id immediately and
the work continues in the background. Callers poll GET /jobs/{id}.
"""

import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from crew_runner import run_research
from redaction import redact

# ── logging ──────────────────────────────────────────────────────────────
# Plain stdout logging: App Runner forwards stdout to CloudWatch Logs, so
# anything printed here is searchable there without extra wiring. Because
# CloudWatch keeps what it is given, every record is redacted on the way out.


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


_handler = logging.StreamHandler(stream=sys.stdout)
_handler.setFormatter(_RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler], force=True)
logger = logging.getLogger("research-api")

app = FastAPI(
    title="Research API",
    version="1.0.0",
    description="Multi-agent research pipeline exposed as an asynchronous job API.",
)

S3_BUCKET = os.getenv("S3_BUCKET", "")

_s3 = None
if S3_BUCKET:
    import boto3  # imported lazily so local runs need no AWS credentials

    _s3 = boto3.client("s3")
    logger.info("s3 persistence enabled bucket=%s", S3_BUCKET)
else:
    logger.info("s3 persistence disabled; reports kept in memory only")

# Job state lives in this process. It is lost on restart, and it does not work
# across more than one instance. That is an accepted trade-off for now; moving
# it to DynamoDB is the next step and is noted in the README.
JOBS: dict[str, dict] = {}
REPORTS: dict[str, str] = {}


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500, examples=["latest advances in quantum computing"])


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    query: str
    created_at: str
    finished_at: Optional[str] = None
    report_key: Optional[str] = None
    error: Optional[str] = None


@app.get("/health", tags=["ops"])
def health() -> dict:
    """Liveness probe. App Runner calls this to decide if the instance is healthy."""
    return {"status": "ok", "jobs_in_memory": len(JOBS)}


@app.post("/research", response_model=JobResponse, status_code=202, tags=["research"])
def start_research(req: ResearchRequest, background: BackgroundTasks) -> dict:
    """Accept a research query and start the crew in the background."""
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "job_id": job_id,
        "status": JobStatus.QUEUED,
        "query": req.query,
        "created_at": _now(),
        "finished_at": None,
        "report_key": None,
        "error": None,
    }
    background.add_task(_execute, job_id, req.query)
    logger.info("job accepted job_id=%s query=%r", job_id, req.query)
    return JOBS[job_id]


@app.get("/jobs/{job_id}", response_model=JobResponse, tags=["research"])
def get_job(job_id: str) -> dict:
    """Return the current state of a job."""
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/jobs/{job_id}/report", response_class=PlainTextResponse, tags=["research"])
def get_report(job_id: str) -> str:
    """Return the finished report as markdown."""
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] != JobStatus.DONE:
        raise HTTPException(status_code=409, detail=f"job is {job['status'].value}, not done")

    if job_id in REPORTS:
        return REPORTS[job_id]
    if _s3 and job["report_key"]:
        obj = _s3.get_object(Bucket=S3_BUCKET, Key=job["report_key"])
        return obj["Body"].read().decode("utf-8")
    raise HTTPException(status_code=404, detail="report not available")


# ── internals ────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _execute(job_id: str, query: str) -> None:
    """Run the crew for one job. Any failure is recorded on the job, not raised."""
    JOBS[job_id]["status"] = JobStatus.RUNNING
    logger.info("job running job_id=%s", job_id)

    try:
        report = run_research(query)
        REPORTS[job_id] = report

        if _s3:
            key = f"reports/{job_id}.md"
            _s3.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=report.encode("utf-8"),
                ContentType="text/markdown; charset=utf-8",
            )
            JOBS[job_id]["report_key"] = key
            logger.info("report stored job_id=%s key=%s", job_id, key)

        JOBS[job_id]["status"] = JobStatus.DONE
        logger.info("job done job_id=%s chars=%d", job_id, len(report))

    except Exception as exc:  # noqa: BLE001 - the job records the failure
        JOBS[job_id]["status"] = JobStatus.FAILED
        # The provider puts the API key in the request URL, so an upstream HTTP
        # error carries it in str(exc). This field is served over HTTP by
        # GET /jobs/{id}, so it is redacted before it is stored at all.
        JOBS[job_id]["error"] = redact(f"{type(exc).__name__}: {exc}")[:500]
        logger.exception("job failed job_id=%s", job_id)

    finally:
        JOBS[job_id]["finished_at"] = _now()
