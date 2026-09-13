"""테이블을 모델 정의대로 다시 만든다 (로컬 개발용).

왜 필요한가: main.py는 Alembic 없이 `Base.metadata.create_all`만 쓴다. 이건 **없는
테이블만 만들고, 이미 있는 테이블에는 컬럼을 추가하지 않는다.** 그래서 모델에 컬럼이
늘어난 뒤에도 예전에 만들어둔 DB를 그대로 쓰면 서버는 멀쩡히 뜨는데 INSERT에서
"Unknown column" 류로 터진다 — 원인을 찾기 어려운 자리에서 터지는 게 문제다.

최근 늘어난 컬럼 (이 스크립트를 안 돌리면 기존 DB에 안 생긴다):
  - chat_logs.document_id, chat_logs.answer
  - document_mentor_map.label, document_mentor_map.uploaded_at

실행:
    cd backend
    python scripts/reset_db.py --yes

주의: 해당 DB의 **모든 데이터가 사라진다.** 실수로 배포 DB를 지우지 않도록 접속
대상을 먼저 출력하고 --yes 없이는 아무것도 하지 않는다. ChromaDB(임베딩)는
건드리지 않으므로, 문서를 다시 올릴 거면 CHROMA_PERSIST_DIR도 함께 비우는 게 맞다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from core.database import Base, engine  # noqa: E402

# 모델 모듈을 import해야 Base.metadata에 테이블이 등록된다 (main.py와 같은 이유).
import models.assignment  # noqa: E402, F401
import models.chat  # noqa: E402, F401
import models.report  # noqa: E402, F401
import models.user  # noqa: E402, F401

try:
    import models.checklist  # noqa: F401
    import models.document  # noqa: F401
except ImportError:
    print("경고: models/checklist.py, models/document.py를 찾지 못했습니다.")
    print("      팀원 A 브랜치가 병합되지 않은 상태라면 해당 테이블은 빠집니다.\n")


def main() -> None:
    print(f"대상 DB : {engine.url.render_as_string(hide_password=True)}")
    tables = list(Base.metadata.sorted_tables)
    print(f"테이블  : {len(tables)}개 — {', '.join(t.name for t in tables)}")
    print()

    if "--yes" not in sys.argv:
        print("이 DB의 모든 데이터가 삭제됩니다.")
        print("실행하려면:  python scripts/reset_db.py --yes")
        sys.exit(1)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("완료 — 테이블을 모델 정의대로 다시 만들었습니다.")
    print("시드가 필요하면:  python scripts/seed_local.py")


if __name__ == "__main__":
    main()
