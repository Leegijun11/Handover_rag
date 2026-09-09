"""체크리스트 편집/저장 (담당: 팀원 A) — guidelines 3-5, 3-9, 4-2."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import CurrentUser, get_current_user, require_role, require_self
from core.database import get_db
from models.checklist import ChecklistItemORM
from schemas.checklist import ChecklistItem

router = APIRouter(tags=["checklist"])


# ── 요청 스키마 ──
class ChecklistItemCreate(BaseModel):
    newcomer_id: str
    chapter_id: str | None = None
    title: str
    order: int = 0
    source: str = "manual"


class ChecklistSaveRequest(BaseModel):
    items: list[ChecklistItemCreate]


class ChecklistUpdateRequest(BaseModel):
    title: str | None = None
    chapter_id: str | None = None


class ReorderRequest(BaseModel):
    order: int


class CompleteRequest(BaseModel):
    newcomer_id: str


def _to_schema(row: ChecklistItemORM) -> ChecklistItem:
    return ChecklistItem(
        item_id=row.item_id,
        newcomer_id=row.newcomer_id,
        chapter_id=row.chapter_id,
        title=row.title,
        order=row.order,
        status=row.status,
        completed_at=row.completed_at,
        source=row.source,
    )


# ── API ──
@router.post("/checklist", status_code=201)
def save_checklist(
    payload: ChecklistSaveRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")

    # TODO(A, B와 협의): chapter_id 연결 시 배정문서 챕터인지 검증
    # (챕터의 document_id -> B의 Assignment.document_id 비교 필요, 세부 구현은 B 확정 후 진행)

    rows = []
    for item in payload.items:
        row = ChecklistItemORM(
            item_id=str(uuid.uuid4()),
            newcomer_id=item.newcomer_id,
            chapter_id=item.chapter_id,
            title=item.title,
            order=item.order,
            status="pending",
            completed_at=None,
            source=item.source,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return [_to_schema(r) for r in rows]


@router.get("/checklist")
def list_checklist(
    newcomer_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ChecklistItemORM)
        .filter(ChecklistItemORM.newcomer_id == newcomer_id)
        .order_by(ChecklistItemORM.order)
        .all()
    )
    return [_to_schema(r) for r in rows]


@router.patch("/checklist/{item_id}")
def update_checklist_item(
    item_id: str,
    payload: ChecklistUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")
    row = db.query(ChecklistItemORM).filter(ChecklistItemORM.item_id == item_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    if payload.title is not None:
        row.title = payload.title
    if payload.chapter_id is not None:
        row.chapter_id = payload.chapter_id
    db.commit()
    return _to_schema(row)


@router.patch("/checklist/{item_id}/reorder")
def reorder_checklist_item(
    item_id: str,
    payload: ReorderRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")
    row = db.query(ChecklistItemORM).filter(ChecklistItemORM.item_id == item_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    row.order = payload.order
    db.commit()
    return {"status": "ok"}


@router.post("/checklist/{item_id}/complete")
def complete_checklist_item(
    item_id: str,
    payload: CompleteRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_self(current_user, payload.newcomer_id)

    row = db.query(ChecklistItemORM).filter(ChecklistItemORM.item_id == item_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    row.status = "done"
    row.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "done", "completed_at": row.completed_at}


@router.delete("/checklist/{item_id}", status_code=204)
def delete_checklist_item(
    item_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")
    row = db.query(ChecklistItemORM).filter(ChecklistItemORM.item_id == item_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    db.delete(row)
    db.commit()
    return None


@router.post("/checklist/{item_id}/uncomplete")
def uncomplete_checklist_item(
    item_id: str,
    payload: CompleteRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_self(current_user, payload.newcomer_id)

    row = db.query(ChecklistItemORM).filter(ChecklistItemORM.item_id == item_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    row.status = "pending"
    row.completed_at = None
    db.commit()
    return {"status": "pending", "completed_at": None}