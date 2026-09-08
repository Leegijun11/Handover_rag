"""Assignment 테이블 (담당: LeeJongHoon) — schemas/assignment.py와 1:1 (guidelines 5-3-1)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AssignmentORM(Base):
    __tablename__ = "assignments"

    assignment_id = Column(String(36), primary_key=True, default=_uuid)
    # unique인 이유: 한 신입은 활성 Assignment를 하나만 가진다 (guidelines 2-2).
    # 그래서 재배정은 새 행을 추가하는 게 아니라 이 행의 document_id를 UPDATE하는
    # 방식이어야 하고, 그 규칙을 DB 레벨에서도 강제한다 (guidelines 3-1).
    # 챗봇·리포트가 "이 신입의 문서"를 하나로 특정할 수 있어야 하는 전제이기도 하다.
    newcomer_id = Column(String(36), unique=True, nullable=False)
    mentor_id = Column(String(36), index=True, nullable=False)  # 한 사수가 여러 신입 담당(1:N)
    document_id = Column(String(36), index=True, nullable=False)
    # 최초 배정 시각. 재배정으로 document_id가 바뀌어도 이 값은 갱신하지 않는다 —
    # /report/generate가 최초 리포트의 period_start 기본값으로 쓰는 기준이라,
    # 재배정마다 초기화되면 리포트 기간이 매번 리셋된다 (guidelines 2-2, 3-6).
    assigned_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
