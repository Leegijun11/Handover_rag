"""DocumentChapter/DocumentMentorMap 테이블 (담당: 팀원 A) — schemas/document.py와 1:1 (guidelines 5-3-1)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import Session

from core.database import Base


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
    """document_id -> mentor_id 매핑 (A 내부 전용, 3-9 인증검증용).

    label/uploaded_at 신설 — GET /document?mentor_id= (신규) 목록 화면용. 문서에
    제목 필드가 원래 없어서(2-3), 업로드 시점에 대표 라벨을 한 번 계산해서 여기
    저장해둔다 — 프론트가 브라우저 localStorage로 임시 처리하던 걸 DB로 옮긴 것
    (그래서 다른 브라우저/기기에서 봐도 같은 라벨이 나옴)."""
    __tablename__ = "document_mentor_map"

    document_id = Column(String(36), primary_key=True)
    mentor_id = Column(String(36), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


def get_document_owner(db: Session, document_id: str) -> str | None:
    """이 문서를 업로드한 mentor_id 반환. B의 POST /assignment에서 소유권 검증용."""
    mapping = (
        db.query(DocumentMentorMapORM)
        .filter(DocumentMentorMapORM.document_id == document_id)
        .first()
    )
    return mapping.mentor_id if mapping else None


def list_documents_for_mentor(db: Session, mentor_id: str) -> list[DocumentMentorMapORM]:
    """이 사수가 올린 문서 목록, 최신순. GET /document?mentor_id= 용."""
    return (
        db.query(DocumentMentorMapORM)
        .filter(DocumentMentorMapORM.mentor_id == mentor_id)
        .order_by(DocumentMentorMapORM.uploaded_at.desc())
        .all()
    )