"""Background worker: recurring maintenance scheduling, notifications and reports.

Each job runs per plant in its own transaction, guarded by a PostgreSQL advisory lock so multiple
worker replicas never run the same job concurrently. Every run is recorded in job_runs."""

import logging
import signal
import zlib
from collections.abc import Callable
from datetime import timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, engine
from app.core.logging import configure_logging
from app.models.identity import LoginAttempt, UserSession
from app.models.system import JobRun
from app.models.tenancy import Plant
from app.services import lubrication, pdm, pm
from app.services.common import plant_today, sync_rbac, utcnow
from app.services.notifications import deliver_outbox

log = logging.getLogger("cmms.worker")


def _record(job: str, status: str, details: dict, error: str | None, started) -> None:
    with SessionLocal() as s, s.begin():
        s.add(JobRun(job=job, started_at=started, finished_at=utcnow(), status=status, details=details, error=error))


def run_job(job: str, fn: Callable[[Session, Plant], dict], per_plant: bool = True) -> None:
    started = utcnow()
    results: dict = {}
    errors: list[str] = []
    key = zlib.crc32(job.encode()) & 0x7FFFFFFF
    # Session-level advisory lock held on a dedicated connection for the whole run (all plants).
    with engine.connect() as lock_conn:
        got = lock_conn.execute(text("SELECT pg_try_advisory_lock(1, :k)"), {"k": key}).scalar()
        lock_conn.commit()
        if not got:
            _record(job, "skipped", {"reason": "locked by another worker"}, None, started)
            return
        try:
            with SessionLocal() as db:
                with db.begin():
                    plants = list(db.execute(select(Plant).where(Plant.is_active.is_(True))).scalars()) if per_plant else [None]
                for plant in plants:
                    try:
                        with db.begin():
                            results[plant.code if plant else "global"] = fn(db, plant)  # type: ignore[arg-type]
                    except Exception as e:  # noqa: BLE001 - one plant failing must not stop the others
                        log.exception("job failed", extra={"job": job})
                        errors.append(f"{plant.code if plant else 'global'}: {e}")
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(1, :k)"), {"k": key})
            lock_conn.commit()
    _record(job, "failed" if errors else "success", results, "; ".join(errors) or None, started)


def job_pm(db: Session, plant: Plant) -> dict:
    return pm.run_scheduler(db, plant)


def job_lube(db: Session, plant: Plant) -> dict:
    return {"routes_generated": lubrication.run_routes(db, plant), "missed_flagged": lubrication.flag_missed(db, plant)}


def job_pdm_stale(db: Session, plant: Plant) -> dict:
    return {"marked_unknown": pdm.mark_stale(db, plant)}


def job_email(db: Session, _: Plant) -> dict:
    return deliver_outbox(db)


def job_kpi_snapshot(db: Session, plant: Plant) -> dict:
    from app.api.routers.kpi import snapshot_month

    today = plant_today(plant)
    last = today.replace(day=1) - timedelta(days=1)
    return {"current": snapshot_month(db, plant, today.year, today.month), "previous": snapshot_month(db, plant, last.year, last.month)}


def job_housekeeping(db: Session, _: Plant) -> dict:
    now = utcnow()
    s = db.execute(delete(UserSession).where(UserSession.expires_at < now - timedelta(days=30)))
    a = db.execute(delete(LoginAttempt).where(LoginAttempt.at < now - timedelta(days=90)))
    return {"sessions_purged": s.rowcount, "login_attempts_purged": a.rowcount}  # type: ignore[attr-defined]


def main() -> None:
    configure_logging()
    with SessionLocal() as db, db.begin():
        sync_rbac(db)
    sched = BlockingScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 600})
    sched.add_job(run_job, "interval", minutes=15, args=["pm_scheduler", job_pm], id="pm_scheduler", next_run_time=utcnow())
    sched.add_job(run_job, "interval", minutes=60, args=["lubrication", job_lube], id="lubrication", next_run_time=utcnow())
    sched.add_job(run_job, "interval", minutes=60, args=["pdm_stale", job_pdm_stale], id="pdm_stale")
    sched.add_job(run_job, "interval", minutes=1, args=["email_outbox", job_email, False], id="email_outbox")
    sched.add_job(run_job, "cron", hour=0, minute=17, args=["kpi_snapshot", job_kpi_snapshot], id="kpi_snapshot")
    sched.add_job(run_job, "cron", hour=1, minute=7, args=["housekeeping", job_housekeeping, False], id="housekeeping")
    signal.signal(signal.SIGTERM, lambda *_: sched.shutdown(wait=False))
    log.info("worker started")
    sched.start()


if __name__ == "__main__":
    main()
