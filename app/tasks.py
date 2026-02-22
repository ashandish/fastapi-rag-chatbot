import redis
from typing import Optional, List
from .celery_app import celery
from .embeddings import add_documents_incremental, reset_collection

r = redis.Redis(host="redis", port=6379, db=2, decode_responses=True)

def set_progress(job_id: str, pct: int, status: str = "processing", detail: Optional[str] = None):
    try:
        pct_int = max(0, min(100, int(pct)))
    except Exception:
        pct_int = 0
    r.set(f"job:{job_id}:progress", pct_int)
    r.set(f"job:{job_id}:status", status)
    if detail is not None:
        r.set(f"job:{job_id}:detail", detail)

@celery.task(bind=True)
def process_embeddings(self, job_id: str, file_paths: List[str], action: str = "add"):
    try:
        set_progress(job_id, 1, "processing", "Starting")
        if action == "clean":
            set_progress(job_id, 2, "processing", "Resetting existing collection")
            reset_collection()

        total = len(file_paths) if file_paths else 0
        if total == 0:
            set_progress(job_id, 100, "completed", "No files to process")
            return {"status": "completed", "added": 0}

        def cb(pct, current=None):
            detail = ("Processed: " + str(current)) if current else None
            set_progress(job_id, pct, "processing", detail)

        stats = add_documents_incremental(file_paths, progress_cb=cb)
        set_progress(job_id, 100, "completed", "Added %d chunks" % stats.get("added", 0))
        return {"status": "completed", "added": stats.get("added", 0)}
    except Exception as e:
        set_progress(job_id, 100, "error", str(e))
        raise
