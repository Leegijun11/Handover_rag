from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChatLog(BaseModel):
    log_id: str
    newcomer_id: str
    question: str
    answer: str
    answered: bool
    matched_chapter_id: str | None
    question_type: Literal["fact", "procedure", "judgment", "advanced"]
    created_at: datetime
