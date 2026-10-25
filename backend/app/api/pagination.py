from typing import Any

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


class PageQ:
    def __init__(self, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
        self.limit = limit
        self.offset = offset


def paginate(db: Session, stmt: Select[Any], page: PageQ, schema: Any) -> dict[str, Any]:
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    rows = db.execute(stmt.limit(page.limit).offset(page.offset)).scalars().all()
    return {"items": [schema.model_validate(r) for r in rows], "total": total, "limit": page.limit, "offset": page.offset}
