import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "handover_rag")

DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)

# pool_size(상시 유지) + max_overflow(몰릴 때만 추가로 생성) = 40 — FastAPI가 동기(def)
# 라우터를 돌리는 스레드풀 기본 상한(anyio, 40)과 맞춘 값이다. 요청 하나가 DB 세션을
# 얻으려면 먼저 스레드를 배정받아야 해서, 동시에 DB 커넥션을 쥐고 있을 수 있는 요청 수는
# 스레드풀 크기를 절대 못 넘는다 — 그래서 40이 "이 구조에서 DB 풀이 더 좁은 병목이
# 되지 않게 하는" 정확한 상한선이고, 그 이상은 어차피 못 쓰여서 의미가 없다 (guidelines 5-9).
# 기본값(5+10=15)으로는 동시 요청 16개부터 DB 커넥션을 못 받아 대기하는 걸 부하
# 테스트로 실측 확인함. 배포 시 Railway MySQL의 max_connections이 이 값(40) 이상인지
# 확인 필요 — 담당 팀원 A에게 공유.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=20, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 공용 ORM Base (guidelines 5-3-1). backend/models/*.py는 전부 이 Base를 상속해서
# 테이블을 정의하고, main.py가 그 모듈들을 import한 뒤 Base.metadata.create_all(bind=engine)로
# 실제 테이블을 생성함 (1차 빌드 범위에서는 Alembic 없이 이 방식으로 충분).
Base = declarative_base()


def get_db():
    """FastAPI Depends용 세션 제너레이터. 각 라우터에서 Depends(get_db)로 사용."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
