"""ChecklistItem 테이블 (담당: 팀원 A) — schemas/checklist.py와 1:1 (guidelines 5-3-1)."""

import uuid

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ChecklistItemORM(Base):
    __tablename__ = "checklist_items"

    item_id = Column(String(36), primary_key=True, default=_uuid)
    newcomer_id = Column(String(36), index=True, nullable=False)
    chapter_id = Column(String(36), nullable=True)
    title = Column(String(255), nullable=False)
    order = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")
    completed_at = Column(DateTime, nullable=True)
    source = Column(String(20), nullable=False)  # "manual" | "ai_draft"