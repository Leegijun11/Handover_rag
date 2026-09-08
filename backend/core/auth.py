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
import bcrypt

logger = logging.getLogger(__name__)

# 로컬 개발 편의를 위한 폴백 값. 이 값이 그대로 쓰이면 공개 레포를 본 사람이
# 누구나 mentor 토큰을 위조할 수 있으므로, 폴백이 걸린 경우 부팅 시 경고한다.
_DEFAULT_SECRET_KEY = "dev-secret-change-me"

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or _DEFAULT_SECRET_KEY
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

# 최소 32바이트: PyJWT가 그 미만이면 InsecureKeyLengthWarning을 낸다 (RFC 7518 3.2).
_MIN_SECRET_BYTES = 32

if JWT_SECRET_KEY == _DEFAULT_SECRET_KEY:
    logger.warning(
        "JWT_SECRET_KEY 환경변수가 없어 공개된 기본값을 사용합니다. "
        "이 값은 공개 저장소에 그대로 있으므로 누구나 토큰을 위조할 수 있습니다. "
        "배포 환경(Railway)에서는 반드시 실제 값을 설정하세요 (guidelines 5-4)."
    )
elif len(JWT_SECRET_KEY.encode("utf-8")) < _MIN_SECRET_BYTES:
    logger.warning(
        "JWT_SECRET_KEY가 %d바이트로 짧습니다. %d바이트 이상을 권장합니다 "
        "(python -c \"import secrets; print(secrets.token_urlsafe(48))\").",
        len(JWT_SECRET_KEY.encode("utf-8")),
        _MIN_SECRET_BYTES,
    )

# bcrypt는 72바이트를 넘는 입력을 거부하므로 해싱 전에 잘라낸다.
# 자르는 위치가 해싱/검증에서 동일하므로 비교 결과는 항상 일치한다.
# (라우터에서 비밀번호 길이를 별도로 제한하는 것을 전제로 한 방어 코드)
_BCRYPT_MAX_BYTES = 72

# auto_error=False로 두는 이유: 기본값(True)이면 Authorization 헤더가 없을 때
# FastAPI가 403을 던지는데, guidelines 3-9/5-5는 "헤더 없음/만료/위조 = 401"이다.
# 401과 403을 프론트가 다르게 처리(401은 로그인 화면으로, 403은 권한 없음 안내)하므로
# 여기서 직접 401을 던진다.
_bearer_scheme = HTTPBearer(auto_error=False)


def _to_bcrypt_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """비밀번호를 bcrypt로 해싱한다. 평문은 어디에도 저장하지 않는다 (guidelines 2-1).

    passlib 대신 bcrypt를 직접 쓰는 이유: passlib 1.7.4는 유지보수가 중단되어
    bcrypt 4.1 이상에서 백엔드 감지가 깨진다. 실제로 bcrypt 5.0.0 환경에서
    CryptContext.hash()가 ValueError로 실패하는 것을 확인했다.
    requirements.txt의 passlib 의존성 정리는 조장에게 요청해둔 상태.
    """
    return bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(password), password_hash.encode("utf-8"))
    except ValueError:
        # DB에 저장된 해시가 손상된 경우 예외 대신 인증 실패로 처리한다.
        return False


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


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """모든 보호된 라우터가 공용으로 쓰는 인증 의존성 (guidelines 3-9).

    /user/register, /user/login을 제외한 모든 엔드포인트에서
    `current_user: CurrentUser = Depends(get_current_user)`로 사용.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("인증 토큰이 필요합니다")

    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise _unauthorized("유효하지 않거나 만료된 토큰입니다")

    # 서명은 유효하지만 클레임이 빠진 토큰이면 KeyError -> 500이 되므로 여기서 401로 막는다.
    user_id = payload.get("user_id")
    role = payload.get("role")
    if not user_id or role not in ("newcomer", "mentor"):
        raise _unauthorized("토큰에 사용자 정보가 없습니다")

    return {"user_id": user_id, "role": role}


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
