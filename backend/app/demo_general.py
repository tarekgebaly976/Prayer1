"""Turn the sample paper mill into a general manufacturing plant for the public demo (seed-demo --profile general).

The sample data is built once (app.seed + app.demo_activity) and then renamed here: equipment, codes, departments, work
orders, requests, alerts and notifications. Structure, dates and numbers stay the same, so every KPI is unchanged.
A general plant: production line (mixer, hydraulic press, drying oven, packaging machine), raw material line (crusher,
grinding mill), packing & palletizing, utilities (compressed air, wastewater), electrical & automation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assets import Asset, DowntimeEvent, Meter
from app.models.enums import DepartmentType
from app.models.identity import User
from app.models.inventory import Part, PartUsage
from app.models.lubrication import LubeRoute, LubricationPoint
from app.models.pdm import ConditionAlert, MeasurementPoint
from app.models.pm import JobPlan, JobPlanTask, PMPlan
from app.models.system import Notification
from app.models.tenancy import Department, Organization, Plant
from app.models.workorders import WorkOrder, WorkRequest, WOService

DEPARTMENTS = {  # paper code -> (code, name, Arabic name, type)
    "PM": ("PROD", "Production", "الإنتاج", DepartmentType.PRODUCTION),
    "SP": ("PREP", "Raw Material Preparation", "تحضير المواد الخام", DepartmentType.PRODUCTION),
    "FH": ("PACK", "Packing & Dispatch", "التعبئة والشحن", DepartmentType.PRODUCTION),
    "WWTP": ("WWT", "Wastewater Treatment", "معالجة مياه الصرف", DepartmentType.UTILITIES),
    "EAI": ("ELEC", "Electrical & Automation", "الكهرباء والأتمتة", DepartmentType.MAINTENANCE),
    "UTIL": ("UTIL", "Utilities", "المرافق", DepartmentType.UTILITIES),
}

# Whole values (asset names, makers, models)
EXACT = {
    "Reel": "Packaging Machine",
    "Pulper": "Crusher",
    "Winder": "Palletizer",
    "Valmet": "Line builder (sample)",
    "Andritz": "Mill maker (sample)",
    "Kadant": "SKF",
    "OptiConcept M": "",
    "SymBelt": "",
    "TwinFlo": "",
}

# Codes, longest first (also found inside titles and tags)
CODES = [
    ("PM1-WIRE-UTW-DR1-BRG-DS", "L1-MIX-M1-DRV-BRG-DE"),
    ("PM1-WIRE-UTW-DR1-BRG-TS", "L1-MIX-M1-DRV-BRG-NDE"),
    ("PM1-WIRE-UTW-DR1-GBX", "L1-MIX-M1-DRV-GBX"),
    ("PM1-WIRE-UTW-DR1", "L1-MIX-M1-DRV"),
    ("PM1-WIRE-UTW", "L1-MIX-M1"),
    ("PM1-WIRE", "L1-MIX"),
    ("PM1-PRESS-SHOE-HPU", "L1-FRM-PRS-HPU"),
    ("PM1-PRESS-SHOE", "L1-FRM-PRS"),
    ("PM1-PRESS", "L1-FRM"),
    ("PM1-DRY-G1-CYL01-JNT", "L1-OVN-Z1-FAN1-SEAL"),
    ("PM1-DRY-G1-CYL01", "L1-OVN-Z1-FAN1"),
    ("PM1-DRY-G1", "L1-OVN-Z1"),
    ("PM1-DRY", "L1-OVN"),
    ("PM1-REEL", "L1-PCK"),
    ("SP-L1-PULP-MTR", "L2-CRS-MTR"),
    ("SP-L1-PULP", "L2-CRS"),
    ("SP-L1-REF1", "L2-MILL"),
    ("SP-L1", "L2"),
    ("FH-L1-WIND", "L3-PAL"),
    ("FH-L1", "L3"),
    ("WWTP-L1-AER1", "WWT-BLW1"),
    ("WWTP-L1", "WWT"),
    ("EAI-DCS-SUB1", "ELE-SUB1"),
    ("EAI-DCS", "ELE-PLC"),
    ("LR-PM1-WIRE", "LR-L1-MIX"),
    ("LR-SP-UTIL", "LR-L2-UTIL"),
    ("VIB-DR1-DS", "VIB-MIX-DE"),
    ("TMP-DR1-DS", "TMP-MIX-DE"),
    ("CUR-PULP-MTR", "CUR-CRS-MTR"),
    ("VIB-REF1-NDE", "VIB-MILL-NDE"),
    ("LP-DR1-DS", "LP-MIX-DE"),
    ("LP-DR1-TS", "LP-MIX-NDE"),
    ("LP-REF1-NDE", "LP-MILL-NDE"),
    ("LP-PULP-MTR", "LP-CRS-MTR"),
    ("LP-WIND", "LP-PAL"),
    ("PM-DR1-W", "PM-MIX-W"),
    ("PM-REF1-M", "PM-MILL-M"),
    ("JP-DR-INSP", "JP-MIX-INSP"),
    ("SEAL-DR1", "SEAL-MIX"),
    ("PM1", "L1"),
]

# Words and phrases, in order (specific before general)
PHRASES = [
    ("Demo Paper Company (SAMPLE DATA)", "Demo Manufacturing Co. (SAMPLE DATA)"),
    ("Demo Paper Mill (sample data)", "Demo Plant (sample data)"),
    ("Paper Machine 1", "Production Line 1"),
    ("Wire Part (Forming Section)", "Mixing Section"),
    ("Under Top Wire", "Main Mixer"),
    ("Drive Roll No. 1 Bearing (Drive Side)", "Mixer Drive Bearing (Drive End)"),
    ("Drive Roll No. 1 Bearing (Tending Side)", "Mixer Drive Bearing (Non-Drive End)"),
    ("Drive Roll No. 1 Gearbox", "Mixer Gearbox"),
    ("Drive Roll No.1 weekly inspection", "Mixer drive weekly inspection"),
    ("Drive Roll No. 1", "Mixer Drive"),
    ("Drive Roll No.1", "Mixer Drive"),
    ("Drive roll weekly inspection", "Mixer drive weekly inspection"),
    ("Drive roll housing seal kit", "Mixer drive seal kit"),
    ("Drive roll", "Mixer drive"),
    ("drive roll", "mixer drive"),
    ("Shoe Press Hydraulic Unit", "Press Hydraulic Power Unit"),
    ("Shoe press belt change (planned stop)", "Hydraulic press overhaul (planned stop)"),
    ("OEM service team, 2 days", "Press maker's service team, 2 days"),
    ("Shoe Press", "Hydraulic Press"),
    ("Shoe press HPU", "Press HPU"),
    ("shoe press", "hydraulic press"),
    ("Press Section", "Forming Section"),
    ("Dryer Section", "Drying Oven"),
    ("Dryer Group 1", "Oven Zone 1"),
    ("Dryer Cylinder 01", "Oven Circulation Fan 1"),
    ("Rotary Joint Cyl 01", "Fan 1 Shaft Seal"),
    ("Rotary joint leaking steam", "Oven fan shaft seal leaking hot air"),
    ("Rotary joint leak, second time this quarter", "Oven fan seal leak, second time this quarter"),
    ("Rotary joint: replace carbon seal ring", "Oven fan: replace shaft seal"),
    ("Steam leak at dryer cylinder 01", "Hot air leak at oven fan 1"),
    ("Visible steam at the joint, hissing noise", "Hot air escaping at the fan shaft, hissing noise"),
    ("Replace dryer doctor blade holder", "Replace oven conveyor belt tracker"),
    ("Dryer group 1 felt change", "Oven conveyor belt change"),
    ("Felt supplier installation", "Belt supplier installation"),
    ("Reel spool arm hydraulic hose replacement", "Packaging machine hydraulic hose replacement"),
    ("Reel spool clamp adjusted: supervisor check", "Packaging machine sealing jaw adjusted: supervisor check"),
    ("Stock Preparation Line 1", "Raw Material Line"),
    ("Pulper Main Motor 800 kW", "Crusher Main Motor 400 kW"),
    ("Pulper discharge valve slow to open", "Crusher discharge gate slow to open"),
    ("Pulper", "Crusher"),
    ("pulper", "crusher"),
    ("Refiner No. 1 monthly inspection", "Grinding mill monthly inspection"),
    ("Refiner No. 1", "Grinding Mill"),
    ("Refiner plates worn, low efficiency and vibration", "Mill liners worn, low output and vibration"),
    ("Replace refiner plates", "Replace mill liners"),
    ("Refiner NDE bearing velocity", "Mill NDE bearing velocity"),
    ("Refiner non-drive-end bearing", "Mill non-drive-end bearing"),
    ("Refiner", "Grinding mill"),
    ("refiner", "grinding mill"),
    ("Finishing Line 1", "Packing & Palletizing Line"),
    ("Finishing line conveyor", "Packing line conveyor"),
    ("Winder drive fault, line stopped", "Palletizer drive fault, line stopped"),
    ("Winder unwind brake overheating", "Palletizer turntable brake overheating"),
    ("Replace worn winder core chuck", "Replace worn palletizer gripper"),
    ("Winder rider roll bearing noise", "Palletizer roller bearing noise"),
    ("Winder drum bearings", "Palletizer roller bearings"),
    ("Winder", "Palletizer"),
    ("winder", "palletizer"),
    ("Effluent Treatment Line", "Wastewater Treatment"),
    ("Distributed Control System", "Plant Control System (PLC/SCADA)"),
    ("DCS screen", "SCADA screen"),
    ("Wire section shutdown inspection", "Mixing section shutdown inspection"),
    ("wire section greasing", "mixing section greasing"),
    ("L1 Shift Leader", "Line 1 Shift Leader"),
    ("near L1 reel", "near the packaging machine"),
    ("in L1 header", "in Line 1 header"),
    ("dr1 drive-side bearing", "mixer drive-end bearing"),
    ("dr1 tending-side bearing", "mixer non-drive-end bearing"),
    ("dr1 ds bearing", "mixer DE bearing"),
    ("dr1 gearbox", "mixer gearbox"),
    ("rotary joint leaking steam", "oven fan shaft seal leaking hot air"),
    ("rotary joint leak", "oven fan seal leak"),
    ("Stock prep and utilities greasing", "Raw material line and utilities greasing"),
    ("DR1 drive-side bearing", "Mixer drive-end bearing"),
    ("DR1 tending-side bearing", "Mixer non-drive-end bearing"),
    ("DR1 DS bearing", "Mixer DE bearing"),
    ("DR1 gearbox", "Mixer gearbox"),
    ("DR1 ", "Mixer "),
    ("DR1", "Mixer"),
    ("Drive-side bearing", "Drive-end bearing"),
    ("Tending-side bearing", "Non-drive-end bearing"),
    ("PM hall", "Production hall"),
    ("SP hall", "Preparation hall"),
    ("FH hall", "Packing hall"),
    ("WWTP hall", "Utilities area"),
    ("EAI hall", "Electrical room"),
    ("UTIL hall", "Utilities area"),
]


def to_general(s: str | None) -> str | None:
    if not s:
        return s
    if s in EXACT:
        return EXACT[s] or None
    for old, new in CODES:
        s = s.replace(old, new)
    for old, new in PHRASES:
        s = s.replace(old, new)
    return s


def generalize(db: Session, plant: Plant) -> None:
    """Rename the demo plant's sample data (built as a paper mill) into a general manufacturing plant, in place."""
    plant.name = to_general(plant.name) or plant.name
    org = db.get(Organization, plant.organization_id)
    if org is not None:
        org.name = to_general(org.name) or org.name
    for d in db.execute(select(Department).where(Department.plant_id == plant.id)).scalars():
        if d.code in DEPARTMENTS:
            d.code, d.name, d.name_ar, d.type = DEPARTMENTS[d.code]
    for u in db.execute(select(User).where(User.organization_id == plant.organization_id)).scalars():
        u.full_name = to_general(u.full_name) or u.full_name
    columns = [
        (Asset, ["code", "name", "oem", "model", "location", "description"]),
        (Meter, ["name"]),
        (Part, ["code", "description"]),
        (JobPlan, ["code", "name", "description"]),
        (PMPlan, ["code", "name"]),
        (LubeRoute, ["code", "name"]),
        (LubricationPoint, ["code", "component"]),
        (MeasurementPoint, ["code", "name", "external_tag"]),
        (ConditionAlert, ["message"]),
        (WorkOrder, ["title", "description", "symptoms", "findings", "corrective_action"]),
        (WorkRequest, ["title", "description", "symptoms"]),
        (DowntimeEvent, ["reason"]),
        (PartUsage, ["description"]),
        (Notification, ["title", "body"]),
    ]
    for model, cols in columns:
        for row in db.execute(select(model).where(model.plant_id == plant.id)).scalars():  # type: ignore[attr-defined]
            for c in cols:
                v = getattr(row, c)
                nv = to_general(v)
                if nv != v and (nv is not None or c not in ("code", "name", "title")):
                    setattr(row, c, nv)
    jp_ids = [j.id for j in db.execute(select(JobPlan).where(JobPlan.plant_id == plant.id)).scalars()]
    for t in db.execute(select(JobPlanTask).where(JobPlanTask.job_plan_id.in_(jp_ids))).scalars():
        t.description = to_general(t.description) or t.description
    wo_ids = select(WorkOrder.id).where(WorkOrder.plant_id == plant.id)
    for sv in db.execute(select(WOService).where(WOService.work_order_id.in_(wo_ids))).scalars():
        sv.description = to_general(sv.description) or sv.description
    db.flush()
