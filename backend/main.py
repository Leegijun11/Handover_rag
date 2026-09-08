"""전체 FastAPI 앱 뼈대 (담당: 조장, guidelines 5-3).

각자 자기 라우터의 import/include 두 줄만 추가하는 방식 — 이 두 줄 외의 임의 수정은
schemas/·core/와 마찬가지로 조장 조율 대상 (guidelines 0, 5-6).
"""

from dotenv import load_dotenv

# core/*.py, routers/*.py가 import되는 시점에 os.getenv(...)로 환경변수를 읽으므로,
# 다른 어떤 import보다도 먼저 .env를 로드해야 함 (guidelines 5-3, A-3 — 이게 없으면
# .env를 채워도 무시되고 JWT_SECRET_KEY 등이 core/auth.py의 기본값으로 조용히 폴백됨).
load_dotenv()

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from core.database import Base, engine  # noqa: E402
from routers.assignment import router as assignment_router  # noqa: E402
from routers.chat import router as chat_router  # noqa: E402
from routers.checklist import router as checklist_router  # noqa: E402
from routers.checklist_draft import router as checklist_draft_router  # noqa: E402
from routers.document import router as document_router  # noqa: E402
from routers.report import router as report_router  # noqa: E402
from routers.user import router as user_router  # noqa: E402

# TODO(각 담당자): backend/models/*.py를 만들면 여기에 import 줄을 추가하세요
# (예: from models.user import UserORM) — Base.metadata.create_all이 이 import들로
# 등록된 테이블만 생성합니다 (guidelines 5-3-1, A-1).
from models.assignment import AssignmentORM  # noqa: E402, F401
from models.chat import ChatLogORM  # noqa: E402, F401
from models.report import AdaptationReportORM, ReportSectionORM  # noqa: E402, F401
from models.user import UserORM  # noqa: E402, F401

app = FastAPI(title="신입 업무보조 챗봇 API")

# 프론트(Vite 개발 서버/Vercel)와 백엔드가 서로 다른 origin이라 CORS 허용 필요.
# 쿠키 대신 Authorization 헤더로만 인증하므로 allow_credentials=False + 와일드카드로 단순화.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# 3-7번 공통 에러 포맷({"error": true, "message": "..."})으로 통일 (guidelines 5-5, A-2).
# FastAPI/slowapi 기본 동작을 그대로 두면 상황별로 바디 모양이 다 달라짐.
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": True, "message": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": True, "message": "요청 형식이 올바르지 않습니다"})


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"error": True, "message": f"요청이 너무 많습니다: {exc.detail}"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # 위 세 핸들러가 못 잡는 나머지 전부(DB 연결 실패 등) — 이게 없으면 FastAPI 기본
    # 500 텍스트 응답("Internal Server Error")으로 새서 3-7번 공통 포맷이 깨짐.
    # 실제로 report/generate를 MySQL 없이 호출했을 때 이 문제가 재현되는 걸 확인하고 추가함.
    import logging

    logging.getLogger("uvicorn.error").error("Unhandled exception on %s %s", request.method, request.url, exc_info=exc)
    return JSONResponse(status_code=500, content={"error": True, "message": "서버 내부 오류가 발생했습니다"})


app.include_router(user_router)
app.include_router(assignment_router)
app.include_router(document_router)
app.include_router(checklist_router)
app.include_router(checklist_draft_router)
app.include_router(chat_router)
app.include_router(report_router)

try:
    Base.metadata.create_all(bind=engine)
except Exception as e:  # noqa: BLE001
    # MySQL이 아직 안 떠 있거나 .env가 안 맞아도 서버 자체는 켜지게 함
    # (guidelines 6-1의 "빈 라우터라도 서버가 켜지는 상태" 원칙 유지) — DB가 필요한
    # 라우트는 이후 실제 요청 시점에 어차피 실패하므로, 여기서는 경고만 남김.
    import logging

    logging.getLogger("uvicorn.error").warning("DB 테이블 생성 실패 (MySQL 연결 확인 필요): %s", e)


@app.get("/")
def health_check():
    """배포 플랫폼 헬스체크용 (guidelines 6-1의 "Hello World 수준 1회 배포 성공 확인")."""
    return {"status": "ok"}
