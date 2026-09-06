from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChecklistItem(BaseModel):
    item_id: str
    newcomer_id: str  # 이 항목이 속한 신입
    chapter_id: str | None  # 사수가 선택적으로 연결
    title: str
    order: int
    status: Literal["pending", "done"]
    completed_at: datetime | None
    source: Literal["manual", "ai_draft"]
