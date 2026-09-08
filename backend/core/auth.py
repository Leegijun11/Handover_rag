"""JWT 발급/검증 + 비밀번호 해싱 + get_current_user 의존성 (담당: 팀원 B).

다른 라우터는 이 모듈의 get_current_user만 가져다 쓰면 됨 (guidelines 3-9).
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Literal, TypedDict

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

# `.env`에 JWT_SECRET_KEY= 처럼 값 없이 키만 있으면 os.getenv가 빈 문자열("")을
# 반환하고, 빈 문자열은 os.getenv의 default 인자를 무시시킴(둘 다 "설정됨" 취급) —
# 그래서 `or`로 빈 문자열도 명시적으로 걸러내야 기본값이 실제로 먹힘.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or "dev-secret-change-me"
if JWT_SECRET_KEY == "dev-secret-change-me":
    logging.getLogger("uvicorn.error").warning(
        "JWT_SECRET_KEY가 설정되지 않아 개발용 기본값을 사용합니다 — 배포 전 .env에 실제 값을 채우세요."
    )
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# deprecated="auto"는 bcrypt가 더 이상 안전하지 않으면 다른 해시 알고리즘으로 자동 전환하도록 함.
_bearer_scheme = HTTPBearer()
# HTTPBearer는 Authorization 헤더에서 Bearer 토큰을 추출하는 FastAPI 의존성 클래스

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


class CurrentUser(TypedDict):
    user_id: str
    role: Literal["newcomer", "mentor"]


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> CurrentUser:
    """모든 보호된 라우터가 공용으로 쓰는 인증 의존성 (guidelines 3-9).

    /user/register, /user/login을 제외한 모든 엔드포인트에서
    `current_user: CurrentUser = Depends(get_current_user)`로 사용.
    """
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않거나 만료된 토큰입니다"
        )
    return {"user_id": payload["user_id"], "role": payload["role"]}


def require_role(current_user: CurrentUser, role: Literal["newcomer", "mentor"]) -> None:
    """mentor 전용 API 등에서 역할을 검증할 때 사용 (guidelines 3-9)."""
    if current_user["role"] != role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"{role} 권한이 필요합니다"
        )


def require_self(current_user: CurrentUser, target_user_id: str) -> None:
    """요청 바디의 newcomer_id/mentor_id가 토큰의 user_id와 같은지 검증 (guidelines 3-9)."""
    if current_user["user_id"] != target_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="본인 명의로만 요청할 수 있습니다"
        )
