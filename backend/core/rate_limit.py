"""slowapi 기반 rate limit 설정 (담당: 조장, guidelines 5-9).

/chat/ask, /checklist/draft, /report/generate에 사용자별 + IP별 제한을 함께 건다 —
사용자별 제한만으로는 이메일 인증이 없어 계정을 계속 새로 만들어 우회하는 걸 막을 수 없기 때문.
각 라우터에서 두 데코레이터를 함께 적용:

    @router.post("/chat/ask")
    @user_limiter.limit(USER_RATE_LIMIT)
    @ip_limiter.limit(IP_RATE_LIMIT)
    def ask(request: Request, ...): ...
"""

import os

import jwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.auth import JWT_ALGORITHM, JWT_SECRET_KEY

# guidelines 5-9 초안 기준치. 실측하며 조정.
USER_RATE_LIMIT = "10/minute"
IP_RATE_LIMIT = "20/minute"

# 데모 계정(6-6 시딩) user_id 목록 — 여러 명이 같은 데모 계정을 동시에 쓰므로
# 이 계정들만 user_id 단독이 아니라 user_id+IP로 키를 나눠서, 접속자별로
# 10/minute를 나눠 갖지 않고 각자 자기 몫을 갖게 함 (guidelines 5-9 항목 6).
_DEMO_USER_IDS = set(filter(None, os.getenv("DEMO_USER_IDS", "").split(",")))


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
    """사용자별 제한용 키 — 토큰이 없으면 IP로 대체.

    데모 계정(_DEMO_USER_IDS)은 예외: user_id만으로 키를 만들면 그 계정을
    동시에 쓰는 모든 방문자가 하나의 10/minute 카운터를 나눠 쓰게 되므로,
    user_id + 방문자 구분값을 합쳐서 방문자별로 카운터를 분리한다.
    방문자 구분값은 프론트가 보내는 X-Visitor-Id 헤더(브라우저별 고유 ID,
    api/client.js 참고)를 우선 쓰고, 없으면 IP로 폴백 — 심사장처럼 여러 명이
    같은 공용 IP(WiFi)를 쓰는 상황에서 IP만으로는 여전히 묶여버리기 때문.
    """
    user_id = _user_id_from_request(request)
    if not user_id:
        return f"ip:{_client_ip(request)}"
    if user_id in _DEMO_USER_IDS:
        visitor = request.headers.get("x-visitor-id") or f"ip:{_client_ip(request)}"
        return f"demo:{user_id}:{visitor}"
    return f"user:{user_id}"


def get_ip_key(request: Request) -> str:
    """IP별 전역 제한용 키 — 계정을 계속 새로 만들어 사용자별 제한을 우회하는 것을 막는 최후 방어선."""
    return _client_ip(request)


user_limiter = Limiter(key_func=get_user_key)
ip_limiter = Limiter(key_func=get_ip_key)
