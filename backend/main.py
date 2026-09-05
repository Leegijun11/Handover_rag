"""전체 FastAPI 앱 뼈대 (담당: 조장, guidelines 5-3).

각자 자기 라우터의 import/include 두 줄만 추가하는 방식 — 이 두 줄 외의 임의 수정은
schemas/·core/와 마찬가지로 조장 조율 대상 (guidelines 0, 5-6).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from core.rate_limit import user_limiter
from routers.assignment import router as assignment_router
from routers.chat import router as chat_router
from routers.checklist import router as checklist_router
from routers.checklist_draft import router as checklist_draft_router
from routers.document import router as document_router
from routers.report import router as report_router
from routers.user import router as user_router

app = FastAPI(title="신입 업무보조 챗봇 API")

# 프론트(Vite 개발 서버/Vercel)와 백엔드가 서로 다른 origin이라 CORS 허용 필요.
# 쿠키 대신 Authorization 헤더로만 인증하므로 allow_credentials=False + 와일드카드로 단순화.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = user_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(user_router)
app.include_router(assignment_router)
app.include_router(document_router)
app.include_router(checklist_router)
app.include_router(checklist_draft_router)
app.include_router(chat_router)
app.include_router(report_router)


@app.get("/")
def health_check():
    """배포 플랫폼 헬스체크용 (guidelines 6-1의 "Hello World 수준 1회 배포 성공 확인")."""
    return {"status": "ok"}
