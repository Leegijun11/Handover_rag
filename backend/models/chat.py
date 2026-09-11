"""ChatLog 테이블 (담당: 조장) — schemas/chat.py와 1:1 (guidelines 5-3-1)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ChatLogORM(Base):
    __tablename__ = "chat_logs"

    log_id = Column(String(36), primary_key=True, default=_uuid)
    newcomer_id = Column(String(36), index=True, nullable=False)
    document_id = Column(String(36), index=True, nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    answered = Column(Boolean, nullable=False)
    matched_chapter_id = Column(String(36), nullable=True)
    question_type = Column(String(20), nullable=False)  # fact/procedure/judgment/advanced
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
