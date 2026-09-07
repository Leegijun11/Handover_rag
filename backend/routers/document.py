"""문서 처리 (담당: 팀원 A) — guidelines 3-2, 3-9, 4-2."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Column, String, Text
from sqlalchemy.orm import Session, declarative_base

from core.auth import CurrentUser, get_current_user, require_role, require_self
from core.database import engine, get_db
from schemas.document import DocumentChapter

router = APIRouter(tags=["document"])

# ── SQLAlchemy 테이블 정의 ──
# TODO(팀): 공용 Base 방식이 확정되면 옮길 것
Base = declarative_base()


def _uuid() -> str:
    return str(uuid.uuid4())


class DocumentChapterORM(Base):
    __tablename__ = "document_chapters"

    chapter_id = Column(String(36), primary_key=True, default=_uuid)
    document_id = Column(String(36), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    parent_id = Column(String(36), nullable=True)
    content = Column(Text, nullable=False)


class DocumentMentorMapORM(Base):
    """document_id -> mentor_id 매핑 (A 내부 전용, 3-9 인증검증용)."""
    __tablename__ = "document_mentor_map"

    document_id = Column(String(36), primary_key=True)
    mentor_id = Column(String(36), nullable=False, index=True)


Base.metadata.create_all(bind=engine)


# ── 요청 스키마 ──
class ChapterInput(BaseModel):
    title: str
    content: str


class UploadChaptersRequest(BaseModel):
    mentor_id: str
    chapters: list[ChapterInput]


# ── API ──
@router.post("/document/upload", status_code=201)
def upload_document(
    payload: UploadChaptersRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")
    require_self(current_user, payload.mentor_id)

    document_id = str(uuid.uuid4())

    # 1. 챕터 저장 (파싱 없이 그대로 — 직접입력 경로)
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

    # 2. document -> mentor 매핑 기록
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