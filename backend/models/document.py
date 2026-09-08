"""DocumentChapter/DocumentMentorMap 테이블 (담당: 팀원 A) — schemas/document.py와 1:1 (guidelines 5-3-1)."""

import uuid

from sqlalchemy import Column, String, Text

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
    """document_id -> mentor_id 매핑 (A 내부 전용, 3-9 인증검증용)."""
    __tablename__ = "document_mentor_map"

    document_id = Column(String(36), primary_key=True)
    mentor_id = Column(String(36), nullable=False, index=True)