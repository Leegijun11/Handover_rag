"""사용자/인증 (담당: LeeJongHoon) — guidelines 3-1, 3-9.

요청 바디 모델은 여기에 둔다. schemas/는 2번 문서(공통 데이터 모델)의 모델을
그대로 담는 곳이고 임의 수정 금지 대상인데, 회원가입 요청 형태는 2번 문서에
없는 이 라우터 전용 입력이라서다 (guidelines 5-2).
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.auth import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from core.database import get_db
from models.user import UserORM
from schemas.user import UserPublic

router = APIRouter(tags=["user"])

# bcrypt가 72바이트를 넘는 입력을 거부한다. core/auth.py가 방어적으로 잘라내긴
# 하지만, 조용히 잘리면 "긴 비밀번호를 정확히 입력했는데 로그인이 되는" 혼란스러운
# 동작이 되므로 여기서 명시적으로 막는다. 한글은 글자당 3바이트라 24자까지다.
_MAX_PASSWORD_BYTES = 72
_MIN_PASSWORD_LENGTH = 8


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # 로그인 식별자로만 사용하며 인증 메일 발송은 2차 확장 항목 (guidelines 2-1, 6-5).
    # 형식 검증은 최소한으로만 한다 — 심사용 데모 가입을 무겁게 만들지 않기 위함.
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH)
    role: Literal["newcomer", "mentor"]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        # 대소문자만 다른 중복 가입을 막기 위해 저장 전에 소문자로 통일한다.
        v = v.strip().lower()
        local, sep, domain = v.partition("@")
        if not (sep and local and "." in domain) or " " in v:
            raise ValueError("이메일 형식이 올바르지 않습니다")
        return v

    @field_validator("password")
    @classmethod
    def check_password_bytes(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _MAX_PASSWORD_BYTES:
            raise ValueError(f"비밀번호는 {_MAX_PASSWORD_BYTES}바이트를 넘을 수 없습니다")
        return v


@router.post("/user/register", status_code=status.HTTP_201_CREATED, response_model=UserPublic)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserORM:
    """이름·이메일·비밀번호·역할로 User 생성 (guidelines 3-1).

    응답 모델이 UserPublic이라 password_hash는 직렬화 대상에서 빠진다 —
    이 필드는 어떤 응답에도 포함하지 않는다 (guidelines 2-1).
    """
    if db.query(UserORM).filter(UserORM.email == payload.email).first() is not None:
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다")

    user = UserORM(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # 위 조회와 INSERT 사이에 같은 이메일이 들어온 경우 — email unique 제약이
        # 최종 방어선이므로, 여기서도 같은 400으로 맞춰준다.
        db.rollback()
        raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다")
    db.refresh(user)
    return user


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserPublic


@router.post("/user/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """이메일+비밀번호 검증 후 JWT 발급 (guidelines 3-1).

    이메일이 없는 경우와 비밀번호가 틀린 경우를 같은 401/같은 문구로 처리한다 —
    구분해서 알려주면 "가입된 이메일인지"를 확인하는 통로가 된다.
    """
    email = payload.email.strip().lower()  # 저장 시에도 소문자로 정규화했다
    user = db.query(UserORM).filter(UserORM.email == email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")

    return LoginResponse(
        access_token=create_access_token(user.user_id, user.role),
        token_type="bearer",
        # UserPublic을 직접 만들어서 password_hash가 응답에 섞일 여지를 없앤다 (guidelines 2-1).
        user=UserPublic(
            user_id=user.user_id, name=user.name, email=user.email, role=user.role
        ),
    )


@router.get("/user/{user_id}", response_model=UserPublic)
def get_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserORM:
    """사용자 단건 조회 (guidelines 3-1).

    본인 확인을 하지 않는 이유: 신입이 자기 사수 이름을 조회하는 플로우가 이 API를
    그대로 쓴다 (guidelines 4-3). 노출 정보가 이름/이메일/역할뿐이라 토큰만 유효하면
    통과시키기로 정해져 있다 (guidelines 3-9).
    """
    user = db.query(UserORM).filter(UserORM.user_id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return user
