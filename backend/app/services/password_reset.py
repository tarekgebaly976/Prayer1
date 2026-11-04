"""Self-service "forgot password": a single-use link by e-mail.

* The answer to a request is always the same, whether or not the address belongs to an account (no account discovery).
* The link works once, for `password_reset_minutes`; asking again cancels earlier links; at most
  `password_reset_per_hour` links per account and hour. Only a SHA-256 digest of the token is stored.
* Setting the new password signs the account out everywhere, lifts a lock-out and e-mails a confirmation.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password, hash_token, new_token, validate_password_strength
from app.models.enums import DeliveryStatus
from app.models.identity import PasswordReset, User, UserSession
from app.models.system import EmailOutbox
from app.services.common import audit, utcnow

_TEXT = {
    "en": {
        "subject": "[PlantPulse] Reset your password",
        "body": "Hello {name},\n\nSomeone (hopefully you) asked to reset the password of your PlantPulse account.\n"
        "Open this link to choose a new password. It works once and for {minutes} minutes:\n\n{link}\n\n"
        "If you did not ask for this, ignore this e-mail: your password stays as it is.",
        "done_subject": "[PlantPulse] Your password was changed",
        "done_body": "Hello {name},\n\nThe password of your PlantPulse account was just changed and you were signed out on "
        "every device.\n\nIf this was not you, tell your administrator at once.",
    },
    "ar": {
        "subject": "[PlantPulse] إعادة تعيين كلمة السر",
        "body": "مرحباً {name}،\n\nطلب أحدٌ (نأمل أن تكون أنت) إعادة تعيين كلمة السر لحسابك في PlantPulse.\n"
        "افتح هذا الرابط لاختيار كلمة سر جديدة. يعمل مرة واحدة ولمدة {minutes} دقيقة:\n\n{link}\n\n"
        "إذا لم تطلب ذلك فتجاهل هذه الرسالة، وستبقى كلمة السر كما هي.",
        "done_subject": "[PlantPulse] تم تغيير كلمة السر",
        "done_body": "مرحباً {name}،\n\nتم تغيير كلمة السر لحسابك في PlantPulse الآن، وتم تسجيل خروجك من كل الأجهزة.\n\n"
        "إذا لم تكن أنت، أبلغ مسؤول النظام فوراً.",
    },
}


def _text(user: User) -> dict[str, str]:
    return _TEXT.get(user.locale, _TEXT["en"])


def _mail(db: Session, to: str, subject: str, body: str) -> None:
    db.add(
        EmailOutbox(to_address=to, subject=subject, body=body, status=DeliveryStatus.PENDING, next_attempt_at=utcnow(), created_at=utcnow())
    )


def request_reset(db: Session, email: str, ip: str | None) -> None:
    """Queue a reset e-mail if the address belongs to an active account. Says nothing either way."""
    s = get_settings()
    if not s.password_reset_enabled:
        return
    now = utcnow()
    user = db.execute(select(User).where(func.lower(User.email) == email.strip().lower())).scalar_one_or_none()
    if user is None or not user.is_active:
        return
    recent = db.execute(
        select(func.count())
        .select_from(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.created_at >= now - timedelta(hours=1))
    ).scalar_one()
    if recent >= s.password_reset_per_hour:
        audit(db, "auth.password_reset_throttled", user_id=user.id, organization_id=user.organization_id, ip=ip)
        return
    # Only the newest link works.
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)).values(expires_at=now))
    token = new_token()
    db.add(
        PasswordReset(
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + timedelta(minutes=s.password_reset_minutes),
            ip=ip,
        )
    )
    t = _text(user)
    link = f"{s.public_url.rstrip('/')}/reset-password?token={token}&lang={user.locale}"  # page opens in the user's language
    _mail(db, user.email, t["subject"], t["body"].format(name=user.full_name, minutes=s.password_reset_minutes, link=link))
    audit(db, "auth.password_reset_requested", user_id=user.id, organization_id=user.organization_id, ip=ip)


class InvalidLink(Exception):
    pass


def complete_reset(db: Session, token: str, new_password: str, ip: str | None) -> None:
    """Set the new password. Raises InvalidLink (unknown, used or expired link) or ValueError (weak password)."""
    now = utcnow()
    row = db.execute(select(PasswordReset).where(PasswordReset.token_hash == hash_token(token)).with_for_update()).scalar_one_or_none()
    user = db.get(User, row.user_id) if row else None
    if row is None or row.used_at is not None or row.expires_at <= now or user is None or not user.is_active:
        raise InvalidLink
    validate_password_strength(new_password)  # the link stays usable if the password is refused
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    user.failed_login_count = 0
    user.locked_until = None
    row.used_at = now
    db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=now))
    t = _text(user)
    _mail(db, user.email, t["done_subject"], t["done_body"].format(name=user.full_name))
    audit(db, "auth.password_reset", user_id=user.id, organization_id=user.organization_id, ip=ip)
