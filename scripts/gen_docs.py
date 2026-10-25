"""Generate docs that must never drift from code: data dictionary + ERD (from SQLAlchemy metadata),
KPI definitions (from app.core.kpi_definitions), role/permission matrix, and Excel import templates.

    cd backend && .venv/bin/python ../scripts/gen_docs.py
"""

import os
import sys

sys.path.insert(0, os.getcwd())
from sqlalchemy import Enum  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.kpi_definitions import KPI_DEFINITIONS  # noqa: E402
from app.core.permissions import PERMISSIONS, ROLES  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.services.imports import TEMPLATES, template_xlsx  # noqa: E402

DOCS = os.path.join(os.path.dirname(os.getcwd()), "docs")
GROUPS = {
    "Tenancy & identity": ["organizations", "plants", "plant_holidays", "departments", "number_sequences", "integration_tokens", "users",
                           "roles", "permissions", "role_permissions", "memberships", "user_sessions", "login_attempts", "user_skills"],
    "Assets": ["assets", "asset_status_history", "asset_bom", "meters", "meter_readings", "failure_codes", "downtime_events"],
    "Work management": ["work_requests", "work_orders", "wo_assignments", "wo_status_history", "wo_status_transitions", "wo_labor",
                        "wo_services", "wo_checklist_items", "wo_comments"],
    "Preventive maintenance": ["job_plans", "job_plan_tasks", "job_plan_materials", "pm_plans", "pm_occurrences"],
    "Lubrication": ["lubricants", "lubricant_alternatives", "lube_routes", "lubrication_points", "lube_tasks"],
    "Shifts & manpower": ["shift_definitions", "shift_patterns", "teams", "team_members", "roster_entries", "shift_handovers"],
    "Inventory & purchasing": ["suppliers", "warehouses", "parts", "part_substitutes", "stock_levels", "inventory_transactions",
                               "reservations", "purchase_orders", "purchase_order_lines", "stockout_events"],
    "Condition monitoring": ["measurement_points", "condition_readings", "condition_alerts"],
    "Shutdowns": ["shutdowns", "shutdown_packages", "package_dependencies", "shutdown_progress_logs", "shutdown_checks"],
    "KPIs, reporting & system": ["production_records", "maintenance_budgets", "kpi_definitions", "kpi_snapshots", "notifications",
                                 "email_outbox", "attachments", "audit_logs", "job_runs"],
}
APPEND_ONLY = {"audit_logs", "inventory_transactions", "wo_status_history", "condition_readings"}


def coltype(c) -> str:  # type: ignore[no-untyped-def]
    if isinstance(c.type, Enum):
        return "enum(" + ", ".join(c.type.enums) + ")"
    return str(c.type).lower()


def dictionary() -> str:
    tables = Base.metadata.tables
    grouped = {t for g in GROUPS.values() for t in g}
    missing = sorted(set(tables) - grouped)
    out = ["# Data dictionary", "", "_Generated from the SQLAlchemy models by `scripts/gen_docs.py` — do not edit by hand._", "",
           f"{len(tables)} tables. Primary keys are UUIDv4 unless noted. All timestamps are `timestamptz` stored in UTC; "
           "due dates are plant-local calendar `date`s. Tables marked **append-only** reject UPDATE/DELETE via trigger "
           "and the runtime role has no UPDATE/DELETE privilege on them.", ""]
    for group, names in list(GROUPS.items()) + ([("Other", missing)] if missing else []):
        out += [f"## {group}", ""]
        for n in names:
            t = tables[n]
            out += [f"### `{n}`" + (" — append-only" if n in APPEND_ONLY else ""), ""]
            doc = (getattr(next((m.class_ for m in Base.registry.mappers if m.local_table is t), None), "__doc__", None) or "").strip()
            if doc:
                out += [" ".join(doc.split()), ""]
            out += ["| Column | Type | Null | Key / reference |", "|---|---|---|---|"]
            for c in t.columns:
                keys = []
                if c.primary_key:
                    keys.append("PK")
                for fk in c.foreign_keys:
                    keys.append(f"FK → {fk.column.table.name}.{fk.column.name} (on delete {fk.ondelete or 'NO ACTION'})")
                out.append(f"| `{c.name}` | {coltype(c)} | {'yes' if c.nullable else 'no'} | {'; '.join(keys)} |")
            uqs = [", ".join(col.name for col in con.columns) for con in t.constraints if con.__class__.__name__ == "UniqueConstraint"]
            cks = [str(con.sqltext) for con in t.constraints if con.__class__.__name__ == "CheckConstraint" and not isinstance(getattr(con, "_type_bound", None), bool) and "IN (" not in str(con.sqltext)]
            idx = [f"{i.name} ({', '.join(c.name for c in i.columns)})" for i in t.indexes]
            if uqs:
                out.append(f"\nUnique: {'; '.join(f'({u})' for u in uqs)}")
            if cks:
                out.append(f"\nChecks: {'; '.join(f'`{c}`' for c in cks)}")
            if idx:
                out.append(f"\nIndexes: {'; '.join(idx)}")
            out.append("")
    return "\n".join(out)


def erd() -> str:
    tables = Base.metadata.tables
    out = ["# Entity-relationship diagrams", "", "_Generated by `scripts/gen_docs.py`. One diagram per domain (Mermaid); "
           "references to tables in other domains are shown as relationships too._", ""]
    for group, names in GROUPS.items():
        out += [f"## {group}", "", "```mermaid", "erDiagram"]
        rels = set()
        for n in names:
            t = tables[n]
            cols = []
            for c in t.columns:
                k = "PK" if c.primary_key else ("FK" if c.foreign_keys else "")
                ty = "enum" if isinstance(c.type, Enum) else str(c.type).split("(")[0].lower().replace(" ", "_")
                cols.append(f"        {ty} {c.name}{(' ' + k) if k else ''}")
            out += [f"    {n} {{", *cols, "    }"]
            for c in t.columns:
                for fk in c.foreign_keys:
                    rels.add(f'    {fk.column.table.name} ||--o{{ {n} : "{c.name}"')
        out += sorted(rels) + ["```", ""]
    return "\n".join(out)


def kpis() -> str:
    out = ["# KPI definitions and formulas", "", "_Generated from `app/core/kpi_definitions.py` (the same text is served by "
           "`GET /api/v1/kpis/definitions` and shown in the dashboard drill-down)._", "",
           "General rules:", "",
           "* KPIs are computed **only from recorded data**. When the inputs are missing, the KPI is returned as "
           "`available: false` with a human-readable `reason`; no value is estimated or defaulted.",
           "* Division by zero never occurs: a zero denominator makes the KPI unavailable.",
           "* Periods are plant-local calendar dates `[start, end]` (inclusive); timestamps are compared in UTC after conversion.",
           "* Scope filters: whole plant, one department, or one asset subtree. Department-restricted users always get their department.",
           "* Every KPI response includes numerator, denominator and drill-down records (capped at 500 rows) for verification.",
           "* Tunable parameters live in `plant.settings.kpi` (e.g. `planned_types`, `emergency_basis`, `include_planned_downtime`, "
           "`capacity_roles`, `lube_tolerance_days`) and `plant.settings.repeat_failure_days`.", ""]
    for i, d in enumerate(KPI_DEFINITIONS, 1):
        out += [f"## {i}. {d['name']} (`{d['code']}`)", "", f"* **Formula:** {d['formula']}", f"* **Unit:** {d['unit']}",
                f"* **Source data:** {d['source_data']}", f"* **Inclusion / exclusion rules:** {d['inclusion_rules']}",
                f"* **Reporting period:** {d['period']}", f"* **Missing / invalid data:** {d['missing_data']}", ""]
    return "\n".join(out)


def roles() -> str:
    codes = list(ROLES)
    out = ["# Roles and permissions", "", "_Generated from `app/core/permissions.py`. Enforced server-side on every endpoint; "
           "the UI only hides what the server would refuse._", "", "| Permission | Description | " + " | ".join(ROLES[c][0] for c in codes) + " |",
           "|---|---|" + "---|" * len(codes)]
    for p, desc in PERMISSIONS.items():
        out.append(f"| `{p}` | {desc} | " + " | ".join("✓" if p in ROLES[c][1] else "" for c in codes) + " |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    for name, fn in (("DATA_DICTIONARY.md", dictionary), ("ERD.md", erd), ("KPI_DEFINITIONS.md", kpis), ("ROLES_PERMISSIONS.md", roles)):
        with open(os.path.join(DOCS, name), "w") as f:
            f.write(fn())
    for kind in TEMPLATES:
        with open(os.path.join(DOCS, "templates", f"{kind}_import_template.xlsx"), "wb") as f:
            f.write(template_xlsx(kind))
    print("generated docs:", sorted(os.listdir(DOCS)))
