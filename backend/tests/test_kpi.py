"""KPI calculations verified against hand-computed values on known records (acceptance H)."""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.db import SessionLocal
from app.models.enums import OccurrenceStatus
from app.models.pm import PMOccurrence
from tests.conftest import mk_asset

TZ = ZoneInfo("Asia/Riyadh")
SEPT = {"start": "2026-09-01", "end": "2026-09-30"}


def _dt(*a):
    return datetime(*a, tzinfo=TZ).isoformat()


def test_reliability_kpis_known_values(world):
    mgr = world.api("manager")
    line = mk_asset(mgr, world, "PM1")
    sup = world.api("mech_sup")
    sup.ok(
        "post",
        f"/assets/{line['id']}/downtime",
        {"started_at": _dt(2026, 9, 5, 10), "ended_at": _dt(2026, 9, 5, 14), "is_failure": True},
        status=201,
    )
    sup.ok(
        "post",
        f"/assets/{line['id']}/downtime",
        {"started_at": _dt(2026, 9, 20, 0), "ended_at": _dt(2026, 9, 20, 6), "is_failure": True, "production_loss_tons": 12.5},
        status=201,
    )
    # overlapping planned stop is excluded by default
    sup.ok(
        "post",
        f"/assets/{line['id']}/downtime",
        {"started_at": _dt(2026, 9, 25, 0), "ended_at": _dt(2026, 9, 25, 8), "is_failure": False, "is_planned": True},
        status=201,
    )
    k = {x["code"]: x for x in mgr.get("/kpis", params=SEPT).json()["kpis"]}
    assert k["mttr"]["value"] == 5.0 and k["mttr"]["denominator"] == 2
    assert k["mtbf"]["value"] == 355.0  # (720 − 10) / 2
    assert k["availability"]["value"] == round(710 / 720 * 100, 2)
    assert k["breakdown_downtime"]["value"] == 10.0 and k["breakdown_downtime"]["details"]["production_loss_tons"] == 12.5
    d = mgr.get("/kpis/mttr", params=SEPT).json()
    assert len(d["records"]) == 2 and d["definition"]["formula"]
    rel = mgr.get(f"/assets/{line['id']}/reliability", params=SEPT).json()
    assert rel["mttr"]["value"] == 5.0
    # no failures in August → MTBF is explicitly unavailable, not zero or infinite
    aug = mgr.get("/kpis/mtbf", params={"start": "2026-08-01", "end": "2026-08-31"}).json()
    assert aug["available"] is False and aug["value"] is None and aug["reason"]


def test_cost_per_ton_budget_and_unavailable(world):
    mgr, sup, tech = world.api("manager"), world.api("mech_sup"), world.api("tech")
    line = mk_asset(mgr, world, "PM1")
    wo = mgr.ok("post", "/work-orders", {"asset_id": line["id"], "type": "emergency", "title": "Couch roll trip"}, status=201)
    sup.ok("post", f"/work-orders/{wo['id']}/assign", {"user_ids": [str(world.users["tech"].id)]})
    tech.ok("post", f"/work-orders/{wo['id']}/status", {"to": "in_progress"})
    tech.ok("post", f"/work-orders/{wo['id']}/labor", {"work_date": "2026-09-10", "hours": 2}, status=201)  # 2 h × 80 = 160
    tech.ok("post", f"/work-orders/{wo['id']}/labor", {"work_date": "2026-09-11", "hours": 1, "is_overtime": True}, status=201)  # 120
    mgr.ok(
        "put",
        "/kpis/production",
        {
            "department_id": str(world.depts["PM"].id),
            "record_date": "2026-09-10",
            "tons_produced": 70,
            "good_tons": 63,
            "planned_production_hours": 24,
            "run_hours": 20,
            "ideal_rate_tph": 4,
        },
    )
    mgr.ok("put", "/kpis/budgets", {"year": 2026, "month": 9, "amount": 1000})
    k = {x["code"]: x for x in mgr.get("/kpis", params=SEPT).json()["kpis"]}
    assert k["cost_per_ton"]["value"] == 4.0  # 280 / 70
    assert k["budget_vs_actual"]["value"] == 28.0 and k["budget_vs_actual"]["details"]["variance"] == 720.0
    # OEE: A = 20/24, P = 70/(20×4), Q = 63/70 → 65.625 %
    assert k["oee"]["value"] == 65.62 or k["oee"]["value"] == 65.63
    assert k["emergency_pct"]["value"] == 100.0
    assert k["planned_maintenance_pct"]["value"] == 0.0
    assert k["cost_by_department"]["details"]["by_department"] == {"PM": 280.0}
    assert k["labor_utilization"]["available"] is False  # no roster recorded → explicitly unavailable
    oct_ = {x["code"]: x for x in mgr.get("/kpis", params={"start": "2026-10-01", "end": "2026-10-20"}).json()["kpis"]}
    assert oct_["cost_per_ton"]["available"] is False and "tonnage" in oct_["cost_per_ton"]["reason"]
    assert oct_["oee"]["available"] is False
    assert oct_["budget_vs_actual"]["available"] is False


def test_pm_compliance_known_records(world):
    planner = world.api("planner")
    line = mk_asset(planner, world, "PM1")
    jp = planner.ok("post", "/pm/job-plans", {"code": "JP", "name": "x"}, status=201)
    plan = planner.ok(
        "post",
        "/pm/plans",
        {
            "code": "P",
            "name": "x",
            "asset_id": line["id"],
            "job_plan_id": jp["id"],
            "frequency_unit": "week",
            "frequency_interval": 1,
            "start_date": "2027-01-01",
            "tolerance_days": 1,
        },
        status=201,
    )
    rows = [  # due, status, completed
        (date(2026, 9, 3), OccurrenceStatus.COMPLETED, date(2026, 9, 3)),  # on time
        (date(2026, 9, 10), OccurrenceStatus.COMPLETED, date(2026, 9, 11)),  # within 1-day tolerance
        (date(2026, 9, 17), OccurrenceStatus.COMPLETED, date(2026, 9, 25)),  # late
        (date(2026, 9, 24), OccurrenceStatus.GENERATED, None),  # missed
        (date(2026, 9, 28), OccurrenceStatus.CANCELLED, None),  # approved cancellation: excluded
    ]
    with SessionLocal() as db, db.begin():
        for due, st, done in rows:
            db.add(
                PMOccurrence(
                    id=uuid.uuid4(),
                    plant_id=world.plant.id,
                    pm_plan_id=uuid.UUID(plan["id"]),
                    occurrence_key=f"T:{due}",
                    due_date=due,
                    original_due_date=due,
                    status=st,
                    completed_date=done,
                )
            )
    k = world.api("manager").get("/kpis/pm_compliance", params=SEPT).json()
    assert k["value"] == 50.0 and k["numerator"] == 2 and k["denominator"] == 4
    assert k["details"] == {"completed_late": 1, "not_completed": 1, "excluded_not_yet_due": 0}
    assert sum(r["compliant"] for r in k["records"]) == 2
    trend = world.api("manager").get("/kpis/trend/pm_compliance", params={"months": 3}).json()
    assert len(trend) == 3 and any(t["period"] == "2026-09" and t["value"] == 50.0 for t in trend)


def test_overdue_and_backlog(world):
    mgr = world.api("manager")
    line = mk_asset(mgr, world, "PM1")
    yesterday = (datetime.now(TZ).date() - timedelta(days=1)).isoformat()
    wo = mgr.ok(
        "post",
        "/work-orders",
        {"asset_id": line["id"], "type": "corrective", "title": "overdue", "due_date": yesterday, "estimated_hours": 10},
        status=201,
    )
    mgr.ok("post", f"/work-orders/{wo['id']}/status", {"to": "approved"})
    mgr.ok("post", "/work-orders", {"asset_id": line["id"], "type": "corrective", "title": "no estimate"}, status=201)
    k = {x["code"]: x for x in mgr.get("/kpis").json()["kpis"]}
    assert k["overdue_work_orders"]["value"] == 1
    assert k["backlog"]["value"] == 10
    # 2 technicians × 8 h × 5 working days = 80 h/week
    assert k["backlog"]["details"]["weekly_capacity_hours"] == 80 and k["backlog"]["details"]["weeks"] == 0.12
    xlsx = mgr.get("/exports/kpis.xlsx")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    assert mgr.get("/reports/kpis.pdf").content[:5] == b"%PDF-"
