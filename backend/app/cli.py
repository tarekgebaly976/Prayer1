"""Operational CLI.

  python -m app.cli bootstrap --org-code ACME --org-name "Acme Paper" --plant-code PM1 --plant-name "Mill 1" \
        --admin-email admin@example.com           # password from CMMS_ADMIN_PASSWORD or interactive prompt
  python -m app.cli seed-demo                     # isolated DEMO organization; password from CMMS_DEMO_PASSWORD
  python -m app.cli reset-password --email admin@example.com   # new password from CMMS_NEW_PASSWORD or prompt
  python -m app.cli sync-rbac
  python -m app.cli run-scheduler [--plant-code X]
  python -m app.cli repair-asset-paths --plant-code PM1 [--apply]   # rebuild asset tree paths from parents
  python -m app.cli spread-lube --plant-code PM1 [--apply]   # one-time: spread never-done lube points over their cycle
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.core.security import hash_password, validate_password_strength
from app.models.enums import DepartmentType
from app.models.identity import Membership, Role, User, UserSession
from app.models.tenancy import Department, Organization, Plant
from app.services.common import sync_rbac, utcnow
from app.services.workflow import ensure_default_transitions

# Departments a new plant starts with: general by default, or a paper mill's areas with --departments paper.
GENERAL_DEPTS = [
    ("PROD", "Production", "الإنتاج", DepartmentType.PRODUCTION),
    ("MAINT", "Maintenance", "الصيانة", DepartmentType.MAINTENANCE),
    ("UTIL", "Utilities", "المرافق", DepartmentType.UTILITIES),
    ("FAC", "Buildings & Facilities", "المباني والمرافق العامة", DepartmentType.FACILITIES),
]
PAPER_DEPTS = [
    ("PM", "Paper Machine", "آلة الورق", DepartmentType.PM),
    ("SP", "Stock Preparation", "تحضير العجينة", DepartmentType.SP),
    ("FH", "Finishing House", "قسم التشطيب", DepartmentType.FH),
    ("WWTP", "Wastewater Treatment Plant", "محطة معالجة مياه الصرف", DepartmentType.WWTP),
    ("EAI", "Electrical, Automation & Instrumentation", "الكهرباء والأتمتة والأجهزة", DepartmentType.EAI),
    ("UTIL", "Utilities & Auxiliary Systems", "المرافق والأنظمة المساعدة", DepartmentType.UTIL),
]


def _password(env: str) -> str:
    if os.environ.get(env):
        validate_password_strength(os.environ[env])
        return os.environ[env]
    # Interactive: typed twice (input is hidden), re-asked until it is strong and both entries match.
    while True:
        pw = getpass.getpass("Password (hidden while typing): ")
        try:
            validate_password_strength(pw)
        except ValueError as e:
            print(f"  {e}. Try again.")
            continue
        if getpass.getpass("Repeat password: ") == pw:
            return pw
        print("  The two entries do not match. Try again.")


def reset_password(a: argparse.Namespace) -> None:
    pw = _password("CMMS_NEW_PASSWORD")
    with SessionLocal() as db, db.begin():
        user = db.execute(select(User).where(User.email == a.email.lower())).scalar_one_or_none()
        if user is None:
            sys.exit(f"No user with e-mail {a.email}")
        user.password_hash = hash_password(pw)
        user.password_changed_at = utcnow()
        user.failed_login_count = 0
        user.locked_until = None
        db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    print(f"Password reset for {a.email}; existing sessions signed out")


def bootstrap(a: argparse.Namespace) -> None:
    pw = _password("CMMS_ADMIN_PASSWORD")
    with SessionLocal() as db, db.begin():
        sync_rbac(db)
        org = db.execute(select(Organization).where(Organization.code == a.org_code)).scalar_one_or_none()
        if org is None:
            org = Organization(code=a.org_code, name=a.org_name)
            db.add(org)
            db.flush()
        plant = db.execute(select(Plant).where(Plant.organization_id == org.id, Plant.code == a.plant_code)).scalar_one_or_none()
        if plant is None:
            plant = Plant(
                organization_id=org.id, code=a.plant_code, name=a.plant_name, timezone=a.timezone, currency=a.currency, settings={}
            )
            db.add(plant)
            db.flush()
            for code, name, ar, t in PAPER_DEPTS if a.departments == "paper" else GENERAL_DEPTS:
                db.add(Department(plant_id=plant.id, code=code, name=name, name_ar=ar, type=t))
            ensure_default_transitions(db, plant.id)
        user = db.execute(select(User).where(User.email == a.admin_email.lower())).scalar_one_or_none()
        if user is None:
            user = User(
                organization_id=org.id,
                email=a.admin_email.lower(),
                full_name="System Administrator",
                password_hash=hash_password(pw),
                is_system_admin=True,
                password_changed_at=utcnow(),
            )
            db.add(user)
            db.flush()
        role = db.execute(select(Role).where(Role.code == "system_admin")).scalar_one()
        if not db.execute(select(Membership).where(Membership.user_id == user.id, Membership.plant_id == plant.id)).first():
            db.add(Membership(user_id=user.id, plant_id=plant.id, role_id=role.id))
    print(f"Bootstrapped organization {a.org_code}, plant {a.plant_code}, admin {a.admin_email}")


def run_sched(a: argparse.Namespace) -> None:
    from app.services.pm import run_scheduler

    with SessionLocal() as db:
        plants = db.execute(select(Plant).where(Plant.is_active.is_(True))).scalars().all()
        for p in plants:
            if a.plant_code and p.code != a.plant_code:
                continue
            with db.begin():
                print(p.code, run_scheduler(db, p))


def spread_lube(a: argparse.Namespace) -> None:
    from app.services.lubrication import spread_due_dates

    with SessionLocal() as db, db.begin():
        plant = db.execute(select(Plant).where(Plant.code == a.plant_code)).scalars().all()
        if len(plant) != 1:
            raise ValueError(f"plant code {a.plant_code!r} matches {len(plant)} plants")
        r = spread_due_dates(db, plant[0], apply=a.apply)
    for k, v in r.items():
        print(f"{k}: {v}")
    if not a.apply:
        print("Dry run only. Add --apply to make these changes.")


def repair_paths(a: argparse.Namespace) -> None:
    from app.services.assets import repair_paths as repair

    with SessionLocal() as db, db.begin():
        plants = db.execute(select(Plant).where(Plant.code == a.plant_code)).scalars().all()
        if len(plants) != 1:
            raise ValueError(f"plant code {a.plant_code!r} matches {len(plants)} plants")
        r = repair(db, plants[0].id, apply=a.apply)
    for k, v in r.items():
        print(f"{k}: {v}")
    if not a.apply and r["paths_wrong"]:
        print("Dry run only. Add --apply to fix them.")


def main() -> None:
    ap = argparse.ArgumentParser(prog="cmms")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap")
    b.add_argument("--org-code", required=True)
    b.add_argument("--org-name", required=True)
    b.add_argument("--plant-code", required=True)
    b.add_argument("--plant-name", required=True)
    b.add_argument("--admin-email", required=True)
    b.add_argument("--timezone", default="Asia/Riyadh")
    b.add_argument("--currency", default="SAR")
    b.add_argument("--departments", choices=["general", "paper"], default="general", help="starting departments")
    rp = sub.add_parser("reset-password")
    rp.add_argument("--email", required=True)
    sub.add_parser("seed-demo")
    sub.add_parser("sync-rbac")
    r = sub.add_parser("run-scheduler")
    r.add_argument("--plant-code")
    rp2 = sub.add_parser("repair-asset-paths")
    rp2.add_argument("--plant-code", required=True)
    rp2.add_argument("--apply", action="store_true")
    sl = sub.add_parser("spread-lube")
    sl.add_argument("--plant-code", required=True)
    sl.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.cmd == "bootstrap":
        bootstrap(a)
    elif a.cmd == "reset-password":
        reset_password(a)
    elif a.cmd == "seed-demo":
        from app.seed import seed_demo

        seed_demo(_password("CMMS_DEMO_PASSWORD"))
    elif a.cmd == "sync-rbac":
        with SessionLocal() as db, db.begin():
            sync_rbac(db)
        print("RBAC synchronised")
    elif a.cmd == "run-scheduler":
        run_sched(a)
    elif a.cmd == "repair-asset-paths":
        repair_paths(a)
    elif a.cmd == "spread-lube":
        spread_lube(a)


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
