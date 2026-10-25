import hashlib
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Ctx, get_ctx, require
from app.core.config import get_settings
from app.core.db import get_db
from app.models.system import Attachment
from app.services.common import audit, utcnow
from app.services.storage import UploadRejected, get_storage, new_key, safe_filename, sniff

router = APIRouter(prefix="/attachments", tags=["attachments"])

# entity type -> (model import path, permission needed to view)
ENTITIES = {
    "asset": ("app.models.assets:Asset", "asset.view"),
    "work_order": ("app.models.workorders:WorkOrder", "wo.view"),
    "shutdown": ("app.models.shutdowns:Shutdown", "shutdown.view"),
    "part": ("app.models.inventory:Part", "inventory.view"),
    "condition_alert": ("app.models.pdm:ConditionAlert", "pdm.view"),
}
CATEGORIES = {"manual", "drawing", "photo", "report", "document", "certificate"}


def _entity(db: Session, ctx: Ctx, entity_type: str, entity_id: uuid.UUID) -> None:
    if entity_type not in ENTITIES:
        raise HTTPException(422, "Unsupported entity type")
    path, perm = ENTITIES[entity_type]
    ctx.require(perm)
    mod, cls = path.split(":")
    model = getattr(__import__(mod, fromlist=[cls]), cls)
    obj = db.get(model, entity_id)
    if obj is None or obj.plant_id != ctx.plant_id:
        raise HTTPException(404, "Entity not found")


@router.post("", status_code=201)
def upload(
    entity_type: str = Form(...),
    entity_id: uuid.UUID = Form(...),
    category: str = Form("document"),
    file: UploadFile = File(...),
    ctx: Ctx = Depends(require("attachment.upload")),
    db: Session = Depends(get_db, scope="function"),
) -> dict:
    if category not in CATEGORIES:
        raise HTTPException(422, "Invalid category")
    _entity(db, ctx, entity_type, entity_id)
    limit = get_settings().max_upload_mb * 1024 * 1024
    name = safe_filename(file.filename or "file")
    sha = hashlib.sha256()
    size = 0
    buf = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    head = b""
    while chunk := file.file.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"File exceeds {get_settings().max_upload_mb} MB")
        if len(head) < 4096:
            head += chunk[: 4096 - len(head)]
        sha.update(chunk)
        buf.write(chunk)
    if size == 0:
        raise HTTPException(422, "Empty file")
    try:
        ctype = sniff(name, head)
    except UploadRejected as e:
        raise HTTPException(415, str(e)) from e
    ext = "." + name.rsplit(".", 1)[-1].lower()
    key = new_key(ctx.plant_id, ext)
    buf.seek(0)
    get_storage().put(key, buf, ctype)  # type: ignore[arg-type]
    a = Attachment(
        plant_id=ctx.plant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        category=category,
        filename=name,
        content_type=ctype,
        size_bytes=size,
        sha256=sha.hexdigest(),
        storage_key=key,
        uploaded_by_id=ctx.user.id,
        created_at=utcnow(),
    )
    db.add(a)
    db.flush()
    audit(
        db,
        "attachment.upload",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        data={"attachment": a.id, "filename": name, "size": size},
    )
    return {"id": a.id, "filename": name, "content_type": ctype, "size_bytes": size}


@router.get("")
def list_attachments(entity_type: str, entity_id: uuid.UUID, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db, scope="function")) -> list[dict]:
    _entity(db, ctx, entity_type, entity_id)
    rows = db.execute(
        select(Attachment)
        .where(
            Attachment.plant_id == ctx.plant_id,
            Attachment.entity_type == entity_type,
            Attachment.entity_id == entity_id,
            Attachment.deleted_at.is_(None),
        )
        .order_by(Attachment.created_at.desc())
    ).scalars()
    return [
        {
            "id": a.id,
            "filename": a.filename,
            "category": a.category,
            "content_type": a.content_type,
            "size_bytes": a.size_bytes,
            "created_at": a.created_at,
        }
        for a in rows
    ]


def _att(db: Session, ctx: Ctx, aid: uuid.UUID) -> Attachment:
    a = db.get(Attachment, aid)
    if a is None or a.plant_id != ctx.plant_id or a.deleted_at is not None:
        raise HTTPException(404, "Attachment not found")
    _entity(db, ctx, a.entity_type, a.entity_id)
    return a


@router.get("/{aid}/download")
def download(aid: uuid.UUID, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db, scope="function"), inline: bool = False):
    a = _att(db, ctx, aid)
    st = get_storage()
    url = st.signed_url(a.storage_key, a.filename)
    if url:
        return RedirectResponse(url, status_code=307)
    disp = "inline" if inline and a.content_type.startswith("image/") or (inline and a.content_type == "application/pdf") else "attachment"
    f = st.open(a.storage_key)
    return StreamingResponse(
        f,
        media_type=a.content_type,
        headers={
            "Content-Disposition": f'{disp}; filename="{a.filename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.delete("/{aid}", status_code=204)
def delete(aid: uuid.UUID, ctx: Ctx = Depends(require("attachment.upload")), db: Session = Depends(get_db, scope="function")) -> None:
    a = _att(db, ctx, aid)
    if a.uploaded_by_id != ctx.user.id and not ctx.has("plant.admin"):
        raise HTTPException(403, "Only the uploader or an administrator can delete")
    a.deleted_at = utcnow()  # soft delete: object retained for audit; purge job may remove after retention
    audit(
        db,
        "attachment.delete",
        user_id=ctx.user.id,
        plant_id=ctx.plant_id,
        entity_type=a.entity_type,
        entity_id=a.entity_id,
        data={"attachment": a.id},
    )
