"""Daily summary e-mail: administrator controls, department scope, once-a-day delivery, never from a test copy."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.enums import WOStatus
from app.models.system import EmailOutbox, Notification
from app.models.tenancy import Plant
from app.models.workorders import WorkOrder
from app.services import daily_summary
from app.services.common import plant_today
from tests.conftest import mk_asset

TZ = ZoneInfo("Asia/Riyadh")


def _wo(api, asset_id, title, wtype="corrective", due=None):
    body = {"asset_id": asset_id, "type": wtype, "title": title}
    if due:
        body["due_date"] = due.isoformat()
    return api.ok("post", "/work-orders", body, status=201)


def _setup(world):
    """PM: one due today, one 3 days overdue, one open breakdown, one finished yesterday. SP: one overdue."""
    admin, planner = world.api("admin"), world.api("planner")
    today = plant_today(world.plant)
    pm = mk_asset(planner, world, "PM1", dept="PM")
    sp = mk_asset(planner, world, "SP1", dept="SP")
    _wo(planner, pm["id"], "Due today", due=today)
    _wo(planner, pm["id"], "Late PM job", due=today - timedelta(days=3))
    _wo(planner, pm["id"], "Couch roll trip", wtype="emergency")
    done = _wo(planner, pm["id"], "Finished yesterday")
    _wo(planner, sp["id"], "Late SP job", due=today - timedelta(days=1))
    with SessionLocal() as db, db.begin():
        db.execute(
            update(WorkOrder)
            .where(WorkOrder.number == done["number"])
            .values(status=WOStatus.COMPLETED, completed_at=datetime.combine(today - timedelta(days=1), time(10), TZ))
        )
    return admin, today


def _run(world, at: time, today):
    with SessionLocal() as db, db.begin():
        plant = db.get(Plant, world.plant.id)
        return daily_summary.run(db, plant, now=datetime.combine(today, at, TZ))


def _summaries(user_id):
    with SessionLocal() as db:
        return list(db.execute(select(Notification).where(Notification.user_id == user_id, Notification.kind == "daily_summary")).scalars())


def test_only_administrators_control_the_daily_summary(world):
    admin, tech, planner = world.api("admin"), world.api("tech"), world.api("planner")
    cfg = admin.ok("get", "/daily-summary")
    assert cfg["enabled"] is False and cfg["send_time"] == "07:00" and cfg["recipients"] == []
    assert tech.get("/daily-summary").status_code == 403
    assert planner.put("/daily-summary", {"enabled": True, "send_time": "06:30"}).status_code == 403
    cfg = admin.ok("put", "/daily-summary", {"enabled": True, "send_time": "06:30"})
    assert cfg["enabled"] is True and cfg["send_time"] == "06:30"

    # Recipients are chosen by user administrators; people cannot add or remove themselves.
    tech_id = str(world.users["tech"].id)
    assert tech.patch(f"/users/{tech_id}", {"daily_summary": True}).status_code == 403
    m = admin.ok("patch", f"/users/{world.users['manager'].id}", {"daily_summary": True})
    assert m["daily_summary"] is True
    admin.ok("patch", f"/users/{world.users['sp_sup'].id}", {"daily_summary": True})
    names = [r["full_name"] for r in admin.ok("get", "/daily-summary")["recipients"]]
    assert names == ["Manager", "SP Supervisor"]
    assert next(u for u in admin.ok("get", "/users") if u["user"]["id"] == tech_id)["daily_summary"] is False
    actions = [a["action"] for a in admin.ok("get", "/audit-logs", params={"action": "daily_summary"})["items"]]
    assert actions == ["daily_summary.update"]


def test_sent_once_after_send_time_scoped_to_departments(world):
    admin, today = _setup(world)
    admin.ok("put", "/daily-summary", {"enabled": True, "send_time": "07:00"})
    for key in ("manager", "sp_sup"):
        admin.ok("patch", f"/users/{world.users[key].id}", {"daily_summary": True})

    assert _run(world, time(6, 55), today) == {"skipped": "not yet"}
    assert _summaries(world.users["manager"].id) == []

    assert _run(world, time(7, 5), today) == {"sent": 2, "recipients": 2}
    # A second check the same day (worker restart, second replica) sends nothing more.
    assert _run(world, time(9, 0), today) == {"sent": 0, "recipients": 2}

    (mgr,) = _summaries(world.users["manager"].id)
    (sp,) = _summaries(world.users["sp_sup"].id)
    assert "Whole plant" in mgr.body and "PM" in mgr.body and "SP" in mgr.body
    assert "2 overdue, 1 breakdowns" in mgr.title  # whole plant: PM + SP overdue
    lines = mgr.body.splitlines()
    plant_block = lines[lines.index("Whole plant") :]
    assert any(ln.split()[-1] == "1" and "Work orders due today" in ln for ln in plant_block[:4])
    assert any("Completed / closed yesterday" in ln and ln.split()[-1] == "1" for ln in plant_block[:8])
    assert "Late PM job" in mgr.body and "3 days" in mgr.body

    # The SP supervisor only sees SP: no PM work, no plant total.
    assert "1 overdue, 0 breakdowns" in sp.title
    assert "Late SP job" in sp.body and "Late PM job" not in sp.body and "Whole plant" not in sp.body
    assert "PM1" not in sp.body

    # Not flagged: nothing.
    assert _summaries(world.users["planner"].id) == []
    with SessionLocal() as db:
        outbox = db.execute(select(EmailOutbox).where(EmailOutbox.subject.startswith("[PlantPulse] Daily summary"))).scalars()
        assert sorted(o.to_address for o in outbox) == ["manager@example.com", "sp_sup@example.com"]


def test_disabled_and_test_copy_send_nothing(world, monkeypatch):
    admin, today = _setup(world)
    admin.ok("patch", f"/users/{world.users['manager'].id}", {"daily_summary": True})
    assert _run(world, time(12), today) == {"skipped": "disabled"}

    admin.ok("put", "/daily-summary", {"enabled": True, "send_time": "07:00"})
    monkeypatch.setattr(get_settings(), "instance_label", "TEST")
    assert "test copy" in _run(world, time(12), today)["skipped"]
    assert admin.ok("get", "/daily-summary")["suppressed"]
    assert _summaries(world.users["manager"].id) == []

    monkeypatch.setattr(get_settings(), "instance_label", "")
    assert _run(world, time(12), today)["sent"] == 1


def test_inactive_member_gets_nothing_and_preview(world):
    admin, today = _setup(world)
    admin.ok("put", "/daily-summary", {"enabled": True, "send_time": "07:00"})
    admin.ok("patch", f"/users/{world.users['sp_sup'].id}", {"daily_summary": True, "is_active": False})
    assert _run(world, time(12), today) == {"sent": 0, "recipients": 0}

    p = admin.ok("get", "/daily-summary/preview", params={"user_id": str(world.users["sp_sup"].id)})
    assert "Late SP job" in p["body"] and "Late PM job" not in p["body"]
    mine = admin.ok("get", "/daily-summary/preview")
    assert "Whole plant" in mine["body"] and "PM compliance" in mine["body"]
    assert _summaries(world.users["admin"].id) == []  # preview never sends
    assert world.api("tech").get("/daily-summary/preview").status_code == 403


def test_arabic_recipient(world):
    admin, today = _setup(world)
    admin.ok("put", "/daily-summary", {"enabled": True, "send_time": "07:00"})
    with SessionLocal() as db, db.begin():
        from app.models.identity import User

        db.get(User, world.users["manager"].id).locale = "ar"
    admin.ok("patch", f"/users/{world.users['manager'].id}", {"daily_summary": True})
    _run(world, time(8), today)
    (n,) = _summaries(world.users["manager"].id)
    assert "الملخص اليومي" in n.title and "المصنع كله" in n.body and "Work orders متأخرة" in n.body


def test_frequency_send_days_chosen_by_administrator(world):
    admin, today = _setup(world)
    wd = today.isoweekday()
    other = wd % 7 + 1
    assert admin.put("/daily-summary", {"enabled": True, "send_time": "07:00", "days": [0]}).status_code == 422
    assert admin.ok("get", "/daily-summary")["days"] == [1, 2, 3, 4, 5, 6, 7]  # default: every day
    cfg = admin.ok("put", "/daily-summary", {"enabled": True, "send_time": "07:00", "days": [other]})
    assert cfg["days"] == [other]
    admin.ok("patch", f"/users/{world.users['manager'].id}", {"daily_summary": True})
    assert _run(world, time(12), today) == {"skipped": "not a send day"}

    # Weekly on today's weekday: "completed" covers the whole week since the previous send day.
    admin.ok("put", "/daily-summary", {"enabled": True, "send_time": "07:00", "days": [wd]})
    assert _run(world, time(12), today)["sent"] == 1
    (n,) = _summaries(world.users["manager"].id)
    assert f"Completed / closed since {(today - timedelta(days=7)).isoformat()}" in n.body
    # Leaving out "days" keeps them.
    assert admin.ok("put", "/daily-summary", {"enabled": False, "send_time": "08:00"})["days"] == [wd]
