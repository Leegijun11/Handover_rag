"""문서 처리 (담당: 팀원 A) — guidelines 3-2, 3-9, 4-2."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import CurrentUser, get_current_user, require_role, require_self
from core.database import get_db
from models.document import DocumentChapterORM, DocumentMentorMapORM
from schemas.document import DocumentChapter

router = APIRouter(tags=["document"])


class ChapterInput(BaseModel):
    title: str
    content: str


class UploadChaptersRequest(BaseModel):
    mentor_id: str
    chapters: list[ChapterInput]


@router.post("/document/upload", status_code=201)
def upload_document(
    payload: UploadChaptersRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")
    require_self(current_user, payload.mentor_id)

    document_id = str(uuid.uuid4())

    chapter_rows = []
    for ch in payload.chapters:
        row = DocumentChapterORM(
            chapter_id=str(uuid.uuid4()),
            document_id=document_id,
            title=ch.title,
            parent_id=None,
            content=ch.content,
        )
        db.add(row)
        chapter_rows.append(row)

    db.add(DocumentMentorMapORM(document_id=document_id, mentor_id=payload.mentor_id))
    db.commit()

    # TODO(A): 다음 커밋에서 이어붙일 부분 —
    #   챕터별 청킹 -> 임베딩 -> ChromaDB 저장

    chapters_response = [
        DocumentChapter(
            chapter_id=r.chapter_id,
            document_id=document_id,
            title=r.title,
            parent_id=r.parent_id,
            content=r.content,
        )
        for r in chapter_rows
    ]
    return {"document_id": document_id, "chapters": chapters_response}