"""Import every model module so Base.metadata is complete (Alembic autogenerate relies on this)."""

from app.models import (  # noqa: F401
    assets,
    identity,
    inventory,
    lubrication,
    pdm,
    pm,
    shifts,
    shutdowns,
    system,
    tenancy,
    workorders,
)
from app.models.base import Base  # noqa: F401
