from datetime import datetime

from pydantic import BaseModel


class Assignment(BaseModel):
    assignment_id: str
    newcomer_id: str  # User.user_id (role="newcomer")
    mentor_id: str  # User.user_id (role="mentor")
    document_id: str  # 이 신입에게 배정된 인수인계서
    assigned_at: datetime  # 최초 배정 시각 — 재배정(문서 교체)해도 값 유지 (guidelines 2-2)
