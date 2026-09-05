"""slowapi 기반 rate limit 설정 (담당: 조장, guidelines 5-9).

/chat/ask, /checklist/draft, /report/generate에 사용자별 + IP별 제한을 함께 건다 —
사용자별 제한만으로는 이메일 인증이 없어 계정을 계속 새로 만들어 우회하는 걸 막을 수 없기 때문.
각 라우터에서 두 데코레이터를 함께 적용:

    @router.post("/chat/ask")
    @user_limiter.limit(USER_RATE_LIMIT)
    @ip_limiter.limit(IP_RATE_LIMIT)
    def ask(request: Request, ...): ...
"""

import jwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.auth import JWT_ALGORITHM, JWT_SECRET_KEY

# guidelines 5-9 초안 기준치. 실측하며 조정.
USER_RATE_LIMIT = "10/minute"
IP_RATE_LIMIT = "20/minute"


def _user_id_from_request(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload["user_id"]
    except jwt.PyJWTError:
        return None


def _client_ip(request: Request) -> str:
    """실제 클라이언트 IP 추출.

    Railway 등 리버스 프록시 뒤에서 배포되면 request.client.host가 프록시
    내부 IP로 찍혀서 모든 사용자가 같은 키로 묶여버림 — X-Forwarded-For를
    우선 사용하고(첫 번째 값 = 원 클라이언트), 없으면(로컬 개발 환경) 기존
    방식(get_remote_address)으로 자동 폴백.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


def get_user_key(request: Request) -> str:
    """사용자별 제한용 키 — 토큰이 없으면 IP로 대체."""
    user_id = _user_id_from_request(request)
    return f"user:{user_id}" if user_id else f"ip:{_client_ip(request)}"


def get_ip_key(request: Request) -> str:
    """IP별 전역 제한용 키 — 계정을 계속 새로 만들어 사용자별 제한을 우회하는 것을 막는 최후 방어선."""
    return _client_ip(request)


user_limiter = Limiter(key_func=get_user_key)
ip_limiter = Limiter(key_func=get_ip_key)
