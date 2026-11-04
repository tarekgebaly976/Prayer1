"""Self-service "forgot password": the e-mailed link, its limits, and what it must never reveal."""

import re

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.identity import PasswordReset
from app.models.system import EmailOutbox
from tests.conftest import PASSWORD, Api, login, make_client

NEW = "Brand-new-Passw0rd!"


@pytest.fixture
def mail_on(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(s, "smtp_from", "noreply@example.com")
    monkeypatch.setattr(s, "public_url", "https://cmms.example.com")
    monkeypatch.setattr(s, "instance_label", "")
    return s


def _anon() -> Api:
    return Api(make_client(), None)


def _mails(to: str) -> list[EmailOutbox]:
    with SessionLocal() as db:
        return list(db.execute(select(EmailOutbox).where(EmailOutbox.to_address == to).order_by(EmailOutbox.created_at)).scalars())


def _token(mail: EmailOutbox) -> str:
    m = re.search(r"https://cmms\.example\.com/reset-password\?token=([\w-]+)&lang=(en|ar|bn)", mail.body)
    assert m, mail.body
    return m.group(1)


def test_forgot_password_link_sets_new_password_once(world, mail_on):
    tech = world.users["tech"]
    old_session = world.api("tech")
    anon = _anon()
    assert anon.get("/meta").json()["password_reset"] is True
    assert anon.post("/auth/forgot-password", {"email": tech.email.upper()}).status_code == 204  # case does not matter
    (mail,) = _mails(tech.email)
    assert "Reset your password" in mail.subject and "30 minutes" in mail.body
    token = _token(mail)
    with SessionLocal() as db:  # only a digest is stored
        assert db.execute(select(PasswordReset.token_hash)).scalar_one() != token

    assert anon.post("/auth/reset-password", {"token": token, "new_password": "short"}).status_code == 422  # policy
    assert anon.post("/auth/reset-password", {"token": token, "new_password": NEW}).status_code == 204
    assert anon.post("/auth/reset-password", {"token": token, "new_password": NEW + "x"}).status_code == 400  # once only

    assert old_session.get("/auth/me").status_code == 401  # signed out everywhere
    assert _anon().post("/auth/login", {"email": tech.email, "password": PASSWORD}).status_code == 401
    login(tech.email, world.plant.id, NEW)
    assert any("password was changed" in m.subject for m in _mails(tech.email))


def test_same_answer_for_unknown_and_inactive_accounts(world, mail_on):
    anon = _anon()
    before = len(_mails("nobody@example.com"))
    assert anon.post("/auth/forgot-password", {"email": "nobody@example.com"}).status_code == 204
    assert len(_mails("nobody@example.com")) == before
    with SessionLocal() as db, db.begin():
        db.get(type(world.users["viewer"]), world.users["viewer"].id).is_active = False
    assert anon.post("/auth/forgot-password", {"email": world.users["viewer"].email}).status_code == 204
    assert _mails(world.users["viewer"].email) == []


def test_new_link_cancels_old_one_and_hourly_limit(world, mail_on):
    email = world.users["planner"].email
    anon = _anon()
    for _ in range(5):
        assert anon.post("/auth/forgot-password", {"email": email}).status_code == 204
    mails = _mails(email)
    assert len(mails) == get_settings().password_reset_per_hour  # at most 3 an hour, the rest silently dropped
    first, last = _token(mails[0]), _token(mails[-1])
    assert anon.post("/auth/reset-password", {"token": first, "new_password": NEW}).status_code == 400  # replaced
    assert anon.post("/auth/reset-password", {"token": last, "new_password": NEW}).status_code == 204


def test_reset_lifts_a_lockout(world, mail_on):
    email = world.users["store"].email
    anon = _anon()
    for _ in range(get_settings().login_max_attempts):
        anon.post("/auth/login", {"email": email, "password": "wrong-password-123"})
    assert anon.post("/auth/login", {"email": email, "password": PASSWORD}).status_code == 429
    anon.post("/auth/forgot-password", {"email": email})
    assert anon.post("/auth/reset-password", {"token": _token(_mails(email)[-1]), "new_password": NEW}).status_code == 204
    login(email, world.plant.id, NEW)


def test_expired_link_is_refused(world, mail_on):
    email = world.users["tech2"].email
    _anon().post("/auth/forgot-password", {"email": email})
    token = _token(_mails(email)[-1])
    with SessionLocal() as db, db.begin():
        row = db.execute(select(PasswordReset)).scalars().one()
        row.expires_at = row.created_at
    assert _anon().post("/auth/reset-password", {"token": token, "new_password": NEW}).status_code == 400


@pytest.mark.parametrize("change", [{"smtp_host": None}, {"public_url": ""}, {"instance_label": "DEMO – sample data"}])
def test_off_without_mail_link_address_or_on_the_demo(world, mail_on, monkeypatch, change):
    for k, v in change.items():
        monkeypatch.setattr(mail_on, k, v)
    anon = _anon()
    assert anon.get("/meta").json()["password_reset"] is False
    email = world.users["tech"].email
    assert anon.post("/auth/forgot-password", {"email": email}).status_code == 204
    assert _mails(email) == []


def test_reset_only_mail_keeps_alerts_in_the_app(world, mail_on, monkeypatch):
    """CMMS_EMAIL_NOTIFICATIONS=false (scripts/main-mail.sh reset-only): alerts stay in the app, reset e-mails still go."""
    from app.models.system import Notification
    from app.services.notifications import notify

    monkeypatch.setattr(mail_on, "email_notifications", False)
    sup = world.users["mech_sup"]
    with SessionLocal() as db, db.begin():
        notify(
            db,
            world.plant.id,
            [sup.id],
            kind="emergency",
            severity="critical",
            title="Emergency breakdown WO-1",
            dedupe_key="t1",
            email=True,
        )
    with SessionLocal() as db:
        assert db.execute(select(Notification).where(Notification.user_id == sup.id)).scalars().first() is not None  # in the app
    assert _mails(sup.email) == []  # but no e-mail
    _anon().post("/auth/forgot-password", {"email": sup.email})
    assert [m.subject for m in _mails(sup.email)] == ["[PlantPulse] Reset your password"]

    monkeypatch.setattr(mail_on, "email_notifications", True)  # "all": the same alert is e-mailed
    with SessionLocal() as db, db.begin():
        notify(
            db,
            world.plant.id,
            [sup.id],
            kind="emergency",
            severity="critical",
            title="Emergency breakdown WO-2",
            dedupe_key="t2",
            email=True,
        )
    assert any("WO-2" in m.subject for m in _mails(sup.email))
