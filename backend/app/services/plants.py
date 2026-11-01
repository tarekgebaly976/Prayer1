"""Creating a plant: an empty plant with its starting departments and the default work-order workflow.
Used by `python -m app.cli bootstrap` and by Admin → Plant → New plant."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.enums import DepartmentType
from app.models.tenancy import Department, Plant
from app.services.workflow import ensure_default_transitions

# Departments a new plant starts with: general by default, a paper mill's areas with "paper", or none.
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
DEPARTMENT_SETS = {"general": GENERAL_DEPTS, "paper": PAPER_DEPTS, "none": []}


def create_plant(
    db: Session,
    organization_id: uuid.UUID,
    code: str,
    name: str,
    timezone: str = "Asia/Riyadh",
    currency: str = "SAR",
    departments: str = "general",
) -> Plant:
    code = code.strip().upper()
    if departments not in DEPARTMENT_SETS:
        raise DomainError("departments must be general, paper or none")
    clash = db.execute(select(Plant.id).where(Plant.organization_id == organization_id, func.upper(Plant.code) == code)).first()
    if clash:
        raise DomainError(f"A plant with code {code} already exists")
    plant = Plant(organization_id=organization_id, code=code, name=name.strip(), timezone=timezone, currency=currency.upper(), settings={})
    db.add(plant)
    db.flush()
    for dcode, dname, ar, t in DEPARTMENT_SETS[departments]:
        db.add(Department(plant_id=plant.id, code=dcode, name=dname, name_ar=ar, type=t))
    ensure_default_transitions(db, plant.id)
    db.flush()
    return plant
