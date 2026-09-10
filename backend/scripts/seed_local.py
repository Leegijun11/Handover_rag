"""로컬 개발용 시드 데이터 (담당: LeeJongHoon).

왜 필요한가: 문서 업로드(/document/upload)가 챕터를 저장하면서 임베딩까지 만들기 때문에
OpenAI 키가 없으면 문서를 하나도 만들 수 없고, 그러면 배정·체크리스트·리포트 화면을
전부 빈 화면으로만 보게 된다. 이 스크립트는 API를 거치지 않고 MySQL에 행을 직접 심어서
키 없이도 화면을 실제 응답으로 검증할 수 있게 한다.

키가 없어도 되는 것 / 안 되는 것:
  - 되는 것 : 로그인, 배정 조회, 챕터 조회, 체크리스트 전체, 리포트 조회
  - 안 되는 것: 챗봇 검색 — ChromaDB에 벡터가 없어서 어떤 질문에도 결과가 안 나온다.
                벡터는 임베딩 API로만 만들 수 있어서 여기서 대신 만들 방법이 없다.

실행:
    cd backend
    python scripts/seed_local.py

같은 id로 여러 번 실행해도 되도록 기존 행을 지우고 다시 넣는다.
6-6의 scripts/seed_demo.py는 이 구조를 그대로 쓰되 회사 3곳 분량으로 늘리고,
문서는 API(/document/upload)를 통해 만들어 임베딩까지 태우면 된다.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

# scripts/ 안에서 실행해도 backend/를 패키지 루트로 잡을 수 있게 한다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from core.auth import hash_password  # noqa: E402
from core.database import SessionLocal  # noqa: E402
from models.assignment import AssignmentORM  # noqa: E402
from models.chat import ChatLogORM  # noqa: E402
from models.report import AdaptationReportORM, ReportSectionORM  # noqa: E402
from models.user import UserORM  # noqa: E402

try:
    from models.checklist import ChecklistItemORM
    from models.document import DocumentChapterORM, DocumentMentorMapORM
except ImportError:  # pragma: no cover - 병합 전 안내
    sys.exit(
        "models/document.py, models/checklist.py가 없습니다.\n"
        "팀원 A 브랜치를 먼저 붙여주세요:  git merge origin/feature/jaehwan"
    )

MENTOR_ID = "local-mentor"
NEWCOMER_ID = "local-newcomer"
DOCUMENT_ID = "local-document"
PASSWORD = "test1234"


def utcnow() -> datetime:
    """서버가 DB에 넣는 값과 같은 형태 — UTC 벽시계 시각의 naive datetime.

    라우터들이 datetime.now(timezone.utc)로 만든 값을 PyMySQL이 tzinfo만 떼고
    저장하므로, 여기서도 같은 기준으로 맞춰야 기간 필터가 어긋나지 않는다.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


CHAPTERS = [
    (
        "1-1 상품 등록 절차",
        "상품은 관리자 페이지 > 상품 > 신규 등록에서 만든다. 카테고리와 과세 여부를 먼저 고르고, "
        "옵션이 있는 상품은 옵션 조합을 만든 뒤에 재고를 넣는다. 대표 이미지는 1000x1000 이상을 쓴다. "
        "등록 직후에는 미노출 상태이며, 검수가 끝나야 노출로 바뀐다.",
    ),
    (
        "2-1 정산 마감 일정",
        "정산 마감은 매월 말일 오후 6시다. 마감 이후에 등록된 건은 다음 달 정산으로 넘어간다. "
        "예외 처리가 필요하면 재무팀에 별도로 요청해야 하고, 요청은 마감 3영업일 전까지 넣는다.",
    ),
    (
        "3-2 반품/교환 처리",
        "반품 요청이 들어오면 먼저 수거 상태를 확인한다. 수거가 완료되어야 환불 버튼이 활성화된다. "
        "고객 귀책이면 왕복 배송비를 차감하고, 상품 하자면 차감하지 않는다.",
    ),
    (
        "4-1 CS 응대 기준",
        "문의는 접수 후 24시간 안에 1차 답변을 보낸다. 확답이 어려운 건도 '확인 중'이라는 답을 먼저 보낸다. "
        "환불·보상 약속은 임의로 하지 않고 반드시 사수에게 확인한다.",
    ),
]


def wipe(db):
    """같은 시드를 다시 심을 수 있도록 이 스크립트가 만든 행만 지운다."""
    db.query(ChatLogORM).filter(ChatLogORM.newcomer_id == NEWCOMER_ID).delete()
    db.query(ChecklistItemORM).filter(ChecklistItemORM.newcomer_id == NEWCOMER_ID).delete()
    db.query(AssignmentORM).filter(AssignmentORM.newcomer_id == NEWCOMER_ID).delete()
    db.query(DocumentChapterORM).filter(DocumentChapterORM.document_id == DOCUMENT_ID).delete()
    db.query(DocumentMentorMapORM).filter(
        DocumentMentorMapORM.document_id == DOCUMENT_ID
    ).delete()

    reports = db.query(AdaptationReportORM).filter(
        AdaptationReportORM.newcomer_id == NEWCOMER_ID
    ).all()
    for report in reports:
        db.query(ReportSectionORM).filter(
            ReportSectionORM.report_id == report.report_id
        ).delete()
        db.delete(report)

    db.query(UserORM).filter(UserORM.user_id.in_([MENTOR_ID, NEWCOMER_ID])).delete(
        synchronize_session=False
    )
    db.commit()


def seed(db):
    now = utcnow()
    assigned_at = now - timedelta(days=14)

    db.add_all(
        [
            UserORM(
                user_id=MENTOR_ID,
                name="김사수",
                email="mentor@test.local",
                password_hash=hash_password(PASSWORD),
                role="mentor",
            ),
            UserORM(
                user_id=NEWCOMER_ID,
                name="박신입",
                email="newcomer@test.local",
                password_hash=hash_password(PASSWORD),
                role="newcomer",
            ),
        ]
    )

    # 문서: 챕터 본문만 MySQL에 넣는다. ChromaDB 벡터는 임베딩 API가 있어야 만들 수 있어서
    # 여기서는 만들지 않는다 — 그래서 이 문서로는 챗봇 검색이 되지 않는다.
    db.add(DocumentMentorMapORM(document_id=DOCUMENT_ID, mentor_id=MENTOR_ID))
    chapter_ids = []
    for title, content in CHAPTERS:
        chapter_id = str(uuid.uuid4())
        chapter_ids.append(chapter_id)
        db.add(
            DocumentChapterORM(
                chapter_id=chapter_id,
                document_id=DOCUMENT_ID,
                title=title,
                parent_id=None,
                content=content,
            )
        )

    db.add(
        AssignmentORM(
            assignment_id=str(uuid.uuid4()),
            newcomer_id=NEWCOMER_ID,
            mentor_id=MENTOR_ID,
            document_id=DOCUMENT_ID,
            assigned_at=assigned_at,
        )
    )

    # 체크리스트: 완료 2 + 미완료 3. 완료 시각이 있어야 리포트의 gap_task가 계산된다.
    items = [
        ("사내 계정 발급받기", None, "manual", True, 11),
        ("정산 마감일 캘린더에 등록하기", chapter_ids[1], "manual", True, 9),
        ("상품 등록 절차 1회 실습해보기", chapter_ids[0], "ai_draft", False, None),
        ("반품 처리 화면 둘러보기", chapter_ids[2], "ai_draft", False, None),
        ("CS 응대 템플릿 읽어보기", chapter_ids[3], "manual", False, None),
    ]
    for order, (title, chapter_id, source, done, days_ago) in enumerate(items, start=1):
        db.add(
            ChecklistItemORM(
                item_id=str(uuid.uuid4()),
                newcomer_id=NEWCOMER_ID,
                chapter_id=chapter_id,
                title=title,
                order=order,
                status="done" if done else "pending",
                completed_at=(now - timedelta(days=days_ago)) if done else None,
                source=source,
            )
        )

    # 질문 로그: 전반부에 몰리고 후반부에 줄어드는 모양으로 넣어서
    # growth_curve / chapter_heatmap / silence_risk가 전부 값을 갖게 한다.
    # (chapter 2-1을 완료 체크한 뒤에도 계속 묻는 로그가 있어야 gap_task도 잡힌다)
    logs = [
        (13, "fact", chapter_ids[0], True),
        (13, "fact", chapter_ids[1], True),
        (12, "fact", chapter_ids[1], True),
        (12, "procedure", chapter_ids[0], True),
        (11, "procedure", chapter_ids[1], True),
        (10, "procedure", chapter_ids[1], True),
        (9, "procedure", chapter_ids[2], True),
        (8, "judgment", chapter_ids[1], True),
        (8, "fact", None, False),
        (7, "judgment", chapter_ids[1], True),
        (7, "procedure", chapter_ids[3], True),
        (3, "judgment", chapter_ids[1], True),
        (1, "advanced", chapter_ids[2], True),
    ]
    for days_ago, question_type, chapter_id, answered in logs:
        db.add(
            ChatLogORM(
                log_id=str(uuid.uuid4()),
                newcomer_id=NEWCOMER_ID,
                question=f"({question_type}) 예시 질문 - {days_ago}일 전",
                answered=answered,
                matched_chapter_id=chapter_id,
                question_type=question_type,
                created_at=now - timedelta(days=days_ago),
            )
        )

    # 리포트 2건. data 모양은 report.py의 계산 함수가 만드는 것과 똑같이 맞춘다 —
    # 화면이 실제 응답과 같은 구조를 받도록 하려는 것이 이 시드의 목적이다.
    heatmap_counts = {chapter_ids[1]: 6, chapter_ids[0]: 2, chapter_ids[2]: 2, chapter_ids[3]: 1}
    _add_report(
        db,
        newcomer_id=NEWCOMER_ID,
        period_start=assigned_at,
        period_end=now - timedelta(days=6),
        generated_at=now - timedelta(days=6),
        sections=[
            (
                "growth_curve",
                "초반에는 사실 확인 위주였고 점차 절차를 묻는 질문으로 옮겨가고 있습니다.",
                {"counts": {"fact": 4, "procedure": 5, "judgment": 2}, "total": 11},
            ),
            (
                "chapter_heatmap",
                "정산 마감 영역에 질문이 몰려 있습니다.",
                {"counts": {chapter_ids[1]: 5, chapter_ids[0]: 2, chapter_ids[2]: 1}},
            ),
            ("gap_task", "아직 판단할 데이터가 부족합니다.", {"gap_items": []}),
            (
                "silence_risk",
                "기간이 짧아 질문 추이를 판단하기 이릅니다.",
                {"first_half_questions": 5, "second_half_questions": 6, "dropped_sharply": False},
            ),
        ],
    )
    _add_report(
        db,
        newcomer_id=NEWCOMER_ID,
        period_start=now - timedelta(days=6),
        period_end=now,
        generated_at=now - timedelta(minutes=30),
        sections=[
            (
                "growth_curve",
                "단순 사실 확인 질문이 줄고 판단이 필요한 질문이 늘고 있습니다. "
                "업무 맥락을 파악해가는 단계로 보입니다.",
                {
                    "counts": {"fact": 3, "procedure": 5, "judgment": 3, "advanced": 1},
                    "total": 12,
                },
            ),
            (
                "chapter_heatmap",
                "정산 관련 업무에 질문이 몰려 있습니다. 문서만으로 파악하기 어려운 영역으로 보입니다.",
                {"counts": heatmap_counts},
            ),
            (
                "gap_task",
                "완료로 체크한 뒤에도 같은 영역을 계속 묻고 있는 항목이 있습니다. "
                "한 번 더 짚어주면 좋겠습니다.",
                {
                    "gap_items": [
                        {"title": "정산 마감일 캘린더에 등록하기", "question_count_after_complete": 3}
                    ]
                },
            ),
            (
                "silence_risk",
                "기간 후반부에 질문이 크게 줄었습니다. 스스로 해결하고 있을 수도 있지만 "
                "막혀서 멈춘 것일 수도 있어 한 번 확인해보시길 권합니다.",
                {"first_half_questions": 9, "second_half_questions": 2, "dropped_sharply": True},
            ),
        ],
    )

    db.commit()
    return chapter_ids


def _add_report(db, *, newcomer_id, period_start, period_end, generated_at, sections):
    report_id = str(uuid.uuid4())
    db.add(
        AdaptationReportORM(
            report_id=report_id,
            newcomer_id=newcomer_id,
            period_start=period_start,
            period_end=period_end,
            generated_at=generated_at,
        )
    )
    for signal_type, summary, data in sections:
        db.add(
            ReportSectionORM(
                section_id=str(uuid.uuid4()),
                report_id=report_id,
                signal_type=signal_type,
                summary=summary,
                data=data,
            )
        )


def main():
    db = SessionLocal()
    try:
        wipe(db)
        seed(db)
    finally:
        db.close()

    print("시드 완료")
    print(f"  사수   mentor@test.local   / {PASSWORD}   (user_id: {MENTOR_ID})")
    print(f"  신입   newcomer@test.local / {PASSWORD}   (user_id: {NEWCOMER_ID})")
    print(f"  문서   {DOCUMENT_ID} — 챕터 {len(CHAPTERS)}개")
    print()
    print("주의: ChromaDB에 벡터가 없어서 챗봇 질문은 답을 찾지 못합니다.")
    print("      임베딩은 OpenAI 키가 있어야 만들 수 있습니다.")


if __name__ == "__main__":
    main()
