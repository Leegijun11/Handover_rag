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

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
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
