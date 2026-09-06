"""사용자/인증 (담당: 팀원 B) — guidelines 3-1, 3-9.

TODO(팀원 B): 아래는 main.py가 부팅되도록 만든 최소 스텁입니다. 직접 채워서 구현하세요.
"""

from fastapi import APIRouter, Depends, HTTPException

from core.auth import CurrentUser, get_current_user

router = APIRouter(tags=["user"])


@router.post("/user/register", status_code=201)
def register():
    # TODO(팀원 B): 이름/이메일/비밀번호/역할 입력받아 User 생성
    # - 이메일 중복 체크, core.auth.hash_password로 비밀번호 해싱
    # - 응답은 UserPublic(schemas/user.py)으로 — password_hash 절대 포함 금지
    raise HTTPException(status_code=501, detail="담당자(팀원 B) 구현 필요")


@router.post("/user/login")
def login():
    # TODO(팀원 B): 이메일+비밀번호 검증 후 core.auth.create_access_token으로 JWT 발급
    # 응답: {"access_token": ..., "token_type": "bearer", "user": UserPublic}
    raise HTTPException(status_code=501, detail="담당자(팀원 B) 구현 필요")


@router.get("/user/{user_id}")
def get_user(user_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(팀원 B): user_id로 User 조회, UserPublic으로 변환해 반환 (password_hash 제외)
    raise HTTPException(status_code=501, detail="담당자(팀원 B) 구현 필요")
