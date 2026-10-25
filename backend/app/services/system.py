import contextlib
import logging
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.models.system import JobRun
from app.services.common import utcnow

log = logging.getLogger("cmms.jobs")


@contextlib.contextmanager
def record_job(db: Session, job: str) -> Iterator[dict]:
    """Records a JobRun row (running → success/failed) for observability."""
    run = JobRun(job=job, started_at=utcnow(), status="running", details={})
    db.add(run)
    db.flush()
    details: dict = {}
    try:
        yield details
        run.status = "skipped" if details.get("skipped") else "success"
        run.details = details
    except Exception as e:
        run.status, run.error = "failed", str(e)[:4000]
        log.exception("job failed", extra={"job": job})
        raise
    finally:
        run.finished_at = utcnow()
