import logging
import smtplib
import ssl
import uuid
from collections.abc import Iterable
from datetime import timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import DeliveryStatus
from app.models.identity import Membership, RolePermission, User
from app.models.system import EmailOutbox, Notification
from app.services.common import utcnow

log = logging.getLogger("cmms.notify")
MAX_ATTEMPTS = 5


def users_with_permission(db: Session, plant_id: uuid.UUID, permission: str) -> list[uuid.UUID]:
    q = (
        select(Membership.user_id)
        .join(RolePermission, RolePermission.role_id == Membership.role_id)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.plant_id == plant_id,
            Membership.is_active.is_(True),
            User.is_active.is_(True),
            RolePermission.permission_code == permission,
        )
    )
    return list(db.execute(q).scalars().unique())


def notify(
    db: Session,
    plant_id: uuid.UUID,
    user_ids: Iterable[uuid.UUID],
    *,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    severity: str = "info",
    dedupe_key: str | None = None,
    email: bool = False,
) -> int:
    """Create in-app notifications (deduplicated by (user, dedupe_key)); optionally queue email."""
    created = 0
    settings = get_settings()
    for uid in set(user_ids):
        nid = uuid.uuid4()
        res = db.execute(
            pg_insert(Notification)
            .values(
                id=nid,
                plant_id=plant_id,
                user_id=uid,
                kind=kind,
                severity=severity,
                title=title,
                body=body,
                link=link,
                dedupe_key=dedupe_key,
                created_at=utcnow(),
            )
            .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
            .returning(Notification.id)
        )
        if res.first() is not None:
            created += 1
            if email:
                user = db.get(User, uid)
                if user:
                    db.add(
                        EmailOutbox(
                            notification_id=nid,
                            to_address=user.email,
                            subject=f"[CMMS] {title}",
                            body=(body or "") + (f"\n\n{link}" if link else ""),
                            status=DeliveryStatus.PENDING if settings.email_enabled else DeliveryStatus.DISABLED,
                            next_attempt_at=utcnow(),
                            created_at=utcnow(),
                        )
                    )
    return created


def notify_permission(db: Session, plant_id: uuid.UUID, permission: str, **kw) -> int:
    return notify(db, plant_id, users_with_permission(db, plant_id, permission), **kw)


def deliver_outbox(db: Session, limit: int = 50) -> dict[str, int]:
    """Send pending emails with exponential-backoff retries. No-op unless SMTP is configured."""
    s = get_settings()
    stats = {"sent": 0, "failed": 0, "retry": 0}
    if not s.email_enabled:
        return stats
    rows = (
        db.execute(
            select(EmailOutbox)
            .where(EmailOutbox.status == DeliveryStatus.PENDING, EmailOutbox.next_attempt_at <= utcnow())
            .order_by(EmailOutbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True, key_share=True)
        )
        .scalars()
        .all()
    )
    for row in rows:
        try:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = s.smtp_from, row.to_address, row.subject
            msg.set_content(row.body)
            with smtplib.SMTP(s.smtp_host or "", s.smtp_port, timeout=20) as smtp:
                if s.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password or "")
                smtp.send_message(msg)
            row.status, row.sent_at = DeliveryStatus.SENT, utcnow()
            stats["sent"] += 1
        except Exception as e:  # noqa: BLE001 - every delivery failure is recorded and retried
            row.attempts += 1
            row.last_error = str(e)[:2000]
            if row.attempts >= MAX_ATTEMPTS:
                row.status = DeliveryStatus.FAILED
                stats["failed"] += 1
            else:
                row.next_attempt_at = utcnow() + timedelta(minutes=2**row.attempts)
                stats["retry"] += 1
            log.warning("email delivery failed", extra={"job": "email"})
    return stats
