"""Assignment 테이블 (담당: LeeJongHoon) — schemas/assignment.py와 1:1 (guidelines 5-3-1)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import Session

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


def get_assignment_by_newcomer(db: Session, newcomer_id: str) -> AssignmentORM | None:
    """신입 1명의 활성 Assignment 조회 — 모듈 간 공용 헬퍼 (guidelines 3-9).

    다른 담당자 라우터는 AssignmentORM을 직접 쿼리하지 말고 이 함수를 쓴다.
    필요한 필드가 담당자마다 달라서 특정 컬럼이 아니라 행 전체를 반환한다.

    - chat.py (조장)      : document_id  — 챗봇 검색 범위 확정 (없으면 404)
    - report.py (조장)    : assigned_at  — 최초 리포트 period_start 기본값
                            mentor_id    — 이 사수가 이 신입 담당인지 검증
    - document.py (팀원 A): document_id  — 챕터 조회 권한 검증
    - checklist.py (팀원 A): document_id — chapter_id가 배정 문서 소속인지 검증

    newcomer_id는 unique 제약이 걸려 있어 결과는 항상 0건 또는 1건이다.
    """
    return db.query(AssignmentORM).filter(AssignmentORM.newcomer_id == newcomer_id).first()
