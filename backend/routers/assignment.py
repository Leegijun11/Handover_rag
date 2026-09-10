"""신입-사수-문서 배정 (담당: LeeJongHoon) — guidelines 3-1, 3-9.

요청 바디 모델은 여기에 둔다 (routers/user.py와 같은 이유 — guidelines 5-2).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import CurrentUser, get_current_user, require_role, require_self
from core.database import get_db
from models.assignment import AssignmentORM, get_assignment_by_newcomer
from models.user import UserORM
from schemas.assignment import Assignment

router = APIRouter(tags=["assignment"])

logger = logging.getLogger("uvicorn.error")


class CreateAssignmentRequest(BaseModel):
    mentor_id: str
    newcomer_id: str
    document_id: str


def _to_assignment(row: AssignmentORM) -> Assignment:
    """ORM 행 -> 응답 스키마. 필드를 직접 나열해서 스키마에 없는 값이 새지 않게 한다."""
    return Assignment(
        assignment_id=row.assignment_id,
        newcomer_id=row.newcomer_id,
        mentor_id=row.mentor_id,
        document_id=row.document_id,
        assigned_at=row.assigned_at,
    )


# 팀원 A 모듈이 아직 없는 상태와 "그런 문서가 없다"를 구분하기 위한 표식.
# 둘 다 None으로 뭉뚱그리면, 병합 후에 존재하지도 않는 document_id로 보낸 배정 요청이
# 소유권 검증을 통과해버린다 (팀원 A의 get_document_owner도 문서가 없으면 None을 준다).
_DOCUMENT_MODULE_MISSING = object()


def _get_document_owner(db: Session, document_id: str):
    """document_id를 업로드한 사수의 user_id (팀원 A 제공, guidelines 3-9).

    반환값은 셋 중 하나다.
      - str                        : 그 문서를 올린 사수의 user_id
      - None                       : 그런 document_id가 없음
      - _DOCUMENT_MODULE_MISSING   : 팀원 A 브랜치 병합 전이라 검증 자체가 불가

    지연 import인 이유: models/document.py는 팀원 A(feature/jaehwan) 소유라 아직 이
    브랜치에 없다. 모듈 최상단에서 import하면 병합 전까지 main.py 자체가 부팅에
    실패한다 (조장이 chat.py/report.py에서 반대 방향 의존성을 처리한 방식과 동일한
    상황). 시그니처는 팀원 A와 합의된 값이라 병합되는 순간 그대로 이어진다.
    """
    try:
        from models.document import get_document_owner
    except ImportError:
        # 병합 전 로컬 개발 한정 — 소유권 검증을 건너뛰고 배정을 허용한다.
        # 이 경고가 배포 로그에 보이면 팀원 A 브랜치가 아직 안 들어온 것이므로,
        # 통합 테스트(guidelines 6-3) 전에 반드시 사라져 있어야 한다.
        logger.warning(
            "models/document.py가 없어 문서 소유권 검증을 건너뜁니다 "
            "(팀원 A 브랜치 병합 전 상태). 통합 테스트 전 반드시 확인할 것."
        )
        return _DOCUMENT_MODULE_MISSING
    return get_document_owner(db, document_id)


@router.post("/assignment", status_code=201, response_model=Assignment)
def create_assignment(
    payload: CreateAssignmentRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Assignment:
    """사수가 업로드한 문서를 특정 신입에게 배정 (guidelines 3-1).

    이미 활성 Assignment가 있는 신입이면 새 행을 만들지 않고 document_id만 교체한다.
    assignment_id/assigned_at은 유지 — assigned_at은 /report/generate가 최초 리포트의
    period_start 기본값으로 쓰는 기준이라, 재배정마다 갱신하면 리포트 기간이 리셋된다
    (guidelines 2-2, 3-1).
    """
    require_role(current_user, "mentor")
    require_self(current_user, payload.mentor_id)

    newcomer = db.query(UserORM).filter(UserORM.user_id == payload.newcomer_id).first()
    if newcomer is None or newcomer.role != "newcomer":
        raise HTTPException(status_code=404, detail="신입 사용자를 찾을 수 없습니다")

    # 남의 document_id를 자기 신입에게 배정하는 것을 막는다. 이 검증이 없으면
    # 사수 아무나 다른 회사 인수인계서를 자기 신입에게 붙일 수 있고, 그 신입은
    # GET /document/{id}/chapters로 본문 전체를 읽게 된다 (guidelines 3-9).
    owner_id = _get_document_owner(db, payload.document_id)
    if owner_id is not _DOCUMENT_MODULE_MISSING:
        if owner_id is None:
            # 없는 문서로 배정하면 그 신입은 챗봇에서 아무것도 못 찾는 상태가 된다.
            # 배정 시점에 막지 않으면 원인을 나중에 챗봇 쪽에서 찾게 된다.
            raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다")
        if owner_id != payload.mentor_id:
            raise HTTPException(
                status_code=403, detail="본인이 업로드한 문서만 배정할 수 있습니다"
            )

    existing = get_assignment_by_newcomer(db, payload.newcomer_id)
    if existing is not None:
        # 다른 사수가 담당 중인 신입은 가져올 수 없다. 3-1의 재배정 규칙이 "document_id만
        # 교체"라 mentor_id를 함께 바꾸는 건 스펙 밖이고, 안 바꾸면 담당 사수와 문서
        # 소유자가 어긋난 행이 남는다. 담당 변경이 필요하면 조장 확인 후 규칙 추가.
        if existing.mentor_id != payload.mentor_id:
            raise HTTPException(
                status_code=403, detail="다른 사수가 담당 중인 신입입니다"
            )
        existing.document_id = payload.document_id
        db.commit()
        db.refresh(existing)
        return _to_assignment(existing)

    assignment = AssignmentORM(
        newcomer_id=payload.newcomer_id,
        mentor_id=payload.mentor_id,
        document_id=payload.document_id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return _to_assignment(assignment)


# response_model=None: 반환 타입이 단건/리스트 유니온이라 그대로 두면 FastAPI가 이걸
# 응답 모델로 추론해서 유니온 검증을 한 번 더 돌린다. 아래에서 이미 Assignment를 직접
# 만들어 반환하므로 얻는 게 없고, 유니온 분기 실패로 500이 날 여지만 생긴다.
@router.get("/assignment", response_model=None)
def get_assignment(
    newcomer_id: str | None = None,
    mentor_id: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Assignment | list[Assignment]:
    """newcomer_id -> 단건, mentor_id -> 리스트 (guidelines 3-1).

    각각 토큰의 user_id와 일치해야 통과한다 — 그 전엔 로그인만 하면 아무 신입/사수의
    배정 정보나 조회할 수 있었다 (guidelines 3-9).
    """
    if (newcomer_id is None) == (mentor_id is None):
        raise HTTPException(
            status_code=400, detail="newcomer_id 또는 mentor_id 중 하나만 지정해야 합니다"
        )

    if newcomer_id is not None:
        require_self(current_user, newcomer_id)
        row = get_assignment_by_newcomer(db, newcomer_id)
        if row is None:
            raise HTTPException(status_code=404, detail="배정된 인수인계서가 없습니다")
        return _to_assignment(row)

    require_role(current_user, "mentor")
    require_self(current_user, mentor_id)
    rows = db.query(AssignmentORM).filter(AssignmentORM.mentor_id == mentor_id).all()
    return [_to_assignment(row) for row in rows]
