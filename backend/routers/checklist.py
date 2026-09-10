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


def _get_assignment(db: Session, newcomer_id: str):
    """models.assignment가 main에 merge되기 전에는 서버가 죽지 않도록 지연 import.
    아직 없으면 None 반환."""
    try:
        from models.assignment import get_assignment_by_newcomer
    except ImportError:
        return None
    return get_assignment_by_newcomer(db, newcomer_id)


# ── API ──
@router.post("/checklist", status_code=201)
def save_checklist(
    payload: ChecklistSaveRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")

    from models.document import DocumentChapterORM

    assignment_cache: dict[str, object] = {}

    def _get_cached_assignment(newcomer_id: str):
        if newcomer_id not in assignment_cache:
            assignment_cache[newcomer_id] = _get_assignment(db, newcomer_id)
        return assignment_cache[newcomer_id]

    for item in payload.items:
        assignment = _get_cached_assignment(item.newcomer_id)
        if assignment is None:
            raise HTTPException(status_code=404, detail="배정된 인수인계서가 없습니다")
        if assignment.mentor_id != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="담당 신입이 아닙니다")

        if item.chapter_id is not None:
            chapter = (
                db.query(DocumentChapterORM)
                .filter_by(chapter_id=item.chapter_id)
                .first()
            )
            if chapter is None or chapter.document_id != assignment.document_id:
                raise HTTPException(status_code=400, detail="배정된 문서의 챕터가 아닙니다")

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

    assignment = _get_assignment(db, row.newcomer_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="배정된 인수인계서가 없습니다")
    if assignment.mentor_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="담당 신입이 아닙니다")

    new_chapter_id = payload.chapter_id if payload.chapter_id is not None else row.chapter_id
    if new_chapter_id is not None:
        from models.document import DocumentChapterORM

        chapter = (
            db.query(DocumentChapterORM)
            .filter_by(chapter_id=new_chapter_id)
            .first()
        )
        if chapter is None or chapter.document_id != assignment.document_id:
            raise HTTPException(status_code=400, detail="배정된 문서의 챕터가 아닙니다")

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