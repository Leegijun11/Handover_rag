"""Demo seed data for the three companies shown on the demo page (guidelines 1-8, 6-6).

회사 3곳이 각자 다른 적응 신호를 보여주도록 설계한 데이터다. 데모 화면(DemoPage.jsx)에
적힌 설명과 맞춘다.

  - 새싹커머스 (a) : 체크리스트 5개, 질문 로그 12건 — 정상적으로 성장하는 신입
  - 한빛물류   (b) : 완료 체크한 업무를 계속 묻는 신입 — gap_task 감지
  - 미래테크   (c) : 기간 후반부에 질문이 끊긴 신입 — silence_risk 급감

OpenAI를 한 번도 부르지 않는다. 그래서 두 가지 한계가 있다.
  1. ChromaDB에 임베딩이 없다 — 데모 신입이 새로 질문하면 검색 결과가 비어서 답을 못 찾는다.
     챗봇을 실제로 시연하려면 같은 문서를 /document/upload로 올려 임베딩을 만들어야 한다(과금).
  2. 리포트의 summary 문장은 사람이 쓴 것이다. 신호 data 값은 report.py의 계산 함수를
     그대로 호출해서 만들었으므로 /report/generate가 계산하는 값과 같다.

사용자 user_id는 고정값이다(demo-mentor-a … demo-newcomer-c). .env의 DEMO_USER_IDS와
일치해야 rate limit이 방문자별로 나뉜다 (guidelines 5-9 항목 6).

실행:
    cd backend
    python scripts/seed_demo.py

같은 id의 기존 데모 행을 지우고 다시 넣으므로 여러 번 실행해도 된다. 데모 계정이 아닌
데이터는 건드리지 않는다.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from core.auth import hash_password  # noqa: E402
from core.database import SessionLocal  # noqa: E402
from models.assignment import AssignmentORM  # noqa: E402
from models.chat import ChatLogORM  # noqa: E402
from models.checklist import ChecklistItemORM  # noqa: E402
from models.document import DocumentChapterORM, DocumentMentorMapORM  # noqa: E402
from models.report import AdaptationReportORM, ReportSectionORM  # noqa: E402
from models.user import UserORM  # noqa: E402

# 리포트 data는 서버와 같은 계산 함수로 만든다 — 손으로 쓰면 실제 생성 결과와 어긋난다.
from routers.report import (  # noqa: E402
    _compute_chapter_heatmap,
    _compute_gap_task,
    _compute_growth_curve,
    _compute_silence_risk,
)

DEMO_PASSWORD = "demo-handover-2026"  # frontend/src/pages/DemoPage.jsx 와 같아야 한다
NO_ANSWER = "문서에 없는 내용이니 담당자에게 문의하세요."  # routers/chat.py NO_ANSWER_MESSAGE


def utcnow() -> datetime:
    """서버가 DB에 쓰는 형태 — UTC 벽시계 시각의 naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


NOW = utcnow().replace(minute=0, second=0, microsecond=0)


def at(days_ago: float, hour: int = 10) -> datetime:
    return (NOW - timedelta(days=days_ago)).replace(hour=hour)


# ── 회사별 데이터 ─────────────────────────────────────────────────
#
# chapters: (key, parent_key, title, content)
#   GET /document/{id}/chapters는 정렬 기준 없이 조회해서 MySQL이 기본키 순서로 준다.
#   그래서 chapter_id를 "demo-a-01", "demo-a-01-1"처럼 문자열 정렬이 목차 순서와 같게 만든다.
#
# logs: (days_ago, hour, chapter_key or None, question_type, question, answer)
#   chapter_key가 None이면 답변 실패(answered=False)로 넣는다.

COMPANIES = [
    {
        "key": "a",
        "company": "새싹커머스",
        "mentor": "김지훈",
        "newcomer": "박서연",
        "label": "새싹커머스 상품운영팀 인수인계서",
        "assigned_days_ago": 21,
        "chapters": [
            ("01", None, "상품 등록",
             "신규 상품은 관리자 페이지에서 등록하고, 검수를 통과해야 판매 페이지에 노출된다.\n\n"
             "등록부터 노출까지 보통 1영업일이 걸리므로 행사 상품은 최소 이틀 전에 등록한다."),
            ("01-1", "01", "상품 등록 절차",
             "관리자 페이지 > 상품 > 신규 등록에서 카테고리와 과세 여부를 먼저 고른다. 카테고리를 "
             "나중에 바꾸면 옵션 정보가 초기화되므로 처음에 정확히 골라야 한다.\n\n"
             "옵션이 있는 상품은 옵션 조합을 먼저 만든 뒤 조합별로 재고를 입력한다. 대표 이미지는 "
             "1000x1000 이상, 배경이 흰색인 컷을 쓴다.\n\n"
             "저장하면 '검수 대기' 상태가 되고, MD 검수가 끝나야 '판매 중'으로 바뀐다."),
            ("01-2", "01", "상품 정보 수정과 판매 중지",
             "가격 변경은 즉시 반영되지만, 상품명과 대표 이미지를 바꾸면 다시 검수를 받는다. "
             "행사 기간 중에는 상품명을 바꾸지 않는다.\n\n"
             "판매 중지는 상품 상세에서 '판매 중지'를 누르면 되고, 이미 들어온 주문은 그대로 출고한다. "
             "완전 삭제는 주문 이력이 없는 상품만 가능하다."),
            ("02", None, "정산",
             "판매 대금 정산은 월 단위로 마감하며, 마감 이후 들어온 건은 다음 달로 넘어간다."),
            ("02-1", "02", "정산 마감 일정",
             "정산 마감은 매월 말일 오후 6시다. 마감 이후 등록되거나 취소된 건은 다음 달 정산에 반영된다.\n\n"
             "마감 3영업일 전에 정산 예정표가 메일로 오며, 금액이 맞지 않으면 그 주 안에 재무팀에 "
             "이의를 올려야 한다."),
            ("02-2", "02", "정산 예외 처리",
             "부분 취소나 교환으로 금액이 바뀐 건은 자동 정산에서 빠진다. 이런 건은 정산 예외 시트에 "
             "주문번호와 사유를 적어 재무팀 담당자에게 공유한다.\n\n"
             "예외 처리 요청은 마감 3영업일 전까지만 받는다. 그 이후는 다음 달로 넘어간다."),
            ("03", None, "반품과 교환",
             "반품 요청이 들어오면 먼저 수거 상태를 확인한다. 수거가 완료되어야 환불 버튼이 활성화된다.\n\n"
             "고객 귀책이면 왕복 배송비를 차감하고, 상품 하자면 차감하지 않는다. 하자 여부가 애매하면 "
             "사진을 받아 사수에게 확인한다."),
        ],
        "checklist": [
            # (title, chapter_key, source, completed_days_ago or None)
            ("상품 등록 절차 읽어보기", "01-1", "manual", 19),
            ("테스트 상품 1건 등록해보기", "01-1", "ai_draft", 16),
            ("정산 마감 일정 캘린더에 등록하기", "02-1", "manual", None),
            ("정산 예외 시트 위치 확인하기", "02-2", "ai_draft", None),
            ("반품 처리 화면 둘러보기", "03", "manual", None),
        ],
        "logs": [
            (20, 10, "01-1", "fact", "상품 등록은 어디서 하나요?",
             "관리자 페이지 > 상품 > 신규 등록에서 합니다. 카테고리와 과세 여부를 먼저 고르세요."),
            (20, 15, "01-1", "fact", "대표 이미지 크기 기준이 있나요?",
             "1000x1000 이상, 배경이 흰색인 컷을 쓰도록 되어 있습니다."),
            (19, 11, "01-1", "procedure", "옵션 있는 상품은 재고를 어떻게 넣어요?",
             "옵션 조합을 먼저 만든 뒤 조합별로 재고를 입력하면 됩니다."),
            (18, 14, "01", "fact", "등록하고 바로 판매되나요?",
             "아닙니다. 검수 대기 상태가 되고 MD 검수를 통과해야 판매 중으로 바뀝니다. 보통 1영업일이 걸립니다."),
            (16, 10, "01-2", "procedure", "상품명을 바꾸면 다시 검수받나요?",
             "네, 상품명과 대표 이미지를 바꾸면 다시 검수를 받습니다. 가격 변경은 즉시 반영됩니다."),
            (14, 16, None, "fact", "택배사 계약 단가는 어디서 봐요?", NO_ANSWER),
            (12, 11, "02-1", "fact", "정산 마감이 언제예요?",
             "매월 말일 오후 6시입니다. 마감 이후 들어온 건은 다음 달 정산에 반영됩니다."),
            (10, 15, "02-2", "procedure", "부분 취소된 주문은 정산을 어떻게 처리하나요?",
             "자동 정산에서 빠지므로 정산 예외 시트에 주문번호와 사유를 적어 재무팀에 공유합니다."),
            (8, 10, "03", "judgment", "고객이 색이 다르다고 반품하면 배송비 차감해야 하나요?",
             "하자 여부가 애매한 경우라 사진을 받아 사수에게 확인하도록 되어 있습니다. 하자로 판단되면 차감하지 않습니다."),
            (6, 14, "02-2", "judgment", "마감 이틀 전에 예외 요청이 오면 받아도 되나요?",
             "예외 처리 요청은 마감 3영업일 전까지만 받습니다. 이틀 전이면 다음 달로 넘어갑니다."),
            (4, 11, "01-2", "judgment", "행사 중인 상품 이름에 오타가 있으면 고쳐도 되나요?",
             "행사 기간 중에는 상품명을 바꾸지 않도록 되어 있습니다. 상품명을 바꾸면 재검수에 들어가기 때문입니다."),
            (2, 16, "02", "advanced", "정산 예정표 금액이 안 맞으면 누구한테 먼저 연락해요?",
             "정산 예정표를 받은 그 주 안에 재무팀에 이의를 올리면 됩니다."),
        ],
        "summaries": {
            "growth_curve": {
                1: "초반에는 등록 위치나 이미지 기준처럼 사실을 확인하는 질문이 대부분이었습니다. 업무 화면에 익숙해지는 단계로 보입니다.",
                2: "사실 확인 질문이 줄고 예외 상황에서 어떻게 판단할지를 묻는 질문이 늘었습니다. 절차를 익히고 실제 사례에 적용하는 단계로 넘어가고 있습니다.",
            },
            "chapter_heatmap": {
                1: "상품 등록 영역에 질문이 집중됐습니다. 첫 주에 맡은 업무와 일치합니다.",
                2: "정산 영역, 특히 예외 처리에 질문이 늘었습니다. 월말 마감을 앞두고 한 번 짚어주면 좋겠습니다.",
            },
            "gap_task": {
                1: "완료 체크한 뒤에도 같은 업무를 다시 묻는 항목은 없습니다.",
                2: "완료 체크한 항목과 이후 질문이 겹치지 않습니다. 체크리스트 진행과 이해도가 맞게 가고 있습니다.",
            },
            "silence_risk": {
                1: "기간 전반과 후반의 질문 수가 비슷합니다. 질문 흐름이 꾸준합니다.",
                2: "질문이 줄지 않고 이어지고 있어 침묵 위험 신호는 없습니다.",
            },
        },
    },
    {
        "key": "b",
        "company": "한빛물류",
        "mentor": "이도현",
        "newcomer": "정민재",
        "label": "한빛물류 배송관제팀 인수인계서",
        "assigned_days_ago": 18,
        "chapters": [
            ("01", None, "배차",
             "당일 배송 물량은 오전 9시 확정 물량을 기준으로 배차하고, 오후 추가분은 예비 차량으로 돌린다."),
            ("01-1", "01", "당일 배차 절차",
             "오전 9시에 WMS에서 권역별 확정 물량을 내려받는다. 권역별 물량을 차량 적재 한도(1톤 기준 "
             "120박스)로 나눠 필요 차량 대수를 계산한다.\n\n"
             "배차표는 관제 시스템의 배차 메뉴에서 기사를 권역에 끌어다 놓는 방식으로 만든다. "
             "저장하면 기사 앱으로 배송 목록이 자동 전송된다.\n\n"
             "배차 확정은 9시 40분까지 끝낸다. 늦어지면 첫 회차 출발이 밀려 오후 배송 전체가 지연된다."),
            ("01-2", "01", "긴급 추가 배차",
             "오후 1시 이후 들어온 긴급 물량은 예비 차량 2대로 처리한다. 예비 차량이 모두 나가 있으면 "
             "용차 업체에 요청하고, 용차 요청은 관제팀장 승인이 필요하다.\n\n"
             "용차 단가는 권역마다 다르므로 요청 전에 단가표를 확인한다."),
            ("02", None, "사고 대응",
             "배송 중 사고는 기사가 앱으로 1차 보고하고, 관제는 접수 후 30분 안에 고객 안내까지 끝낸다."),
            ("02-1", "02", "파손 사고 처리",
             "기사 앱으로 파손 보고가 들어오면 사진을 확인하고 사고 유형을 '파손'으로 접수한다.\n\n"
             "고객에게는 30분 안에 문자로 안내하고, 재발송과 환불 중 고객이 원하는 쪽을 받는다. "
             "재발송이면 당일 긴급 배차로 넘긴다.\n\n"
             "파손 금액이 30만 원을 넘으면 보험 접수 대상이라 사고 보고서를 따로 작성한다."),
            ("02-2", "02", "배송 지연 안내",
             "예정 시간보다 1시간 이상 늦어질 것 같으면 도착 전에 고객에게 먼저 연락한다.\n\n"
             "지연 사유는 '교통 상황' 같은 막연한 표현 대신 예상 도착 시간을 구체적으로 알린다. "
             "2시간 이상 지연이면 쿠폰 지급 대상이다."),
            ("03", None, "마감 보고",
             "오후 7시에 당일 배송 완료율과 사고 건수를 정리해 관제팀 채널에 올린다. "
             "완료율이 95% 미만이면 원인을 한 줄로 함께 적는다."),
        ],
        "checklist": [
            ("당일 배차 절차 읽어보기", "01-1", "manual", 16),
            ("배차표 1회 작성해보기", "01-1", "ai_draft", 13),
            ("파손 사고 처리 절차 읽어보기", "02-1", "manual", 12),
            ("용차 단가표 위치 확인하기", "01-2", "ai_draft", None),
            ("마감 보고 양식 확인하기", "03", "manual", None),
        ],
        # 배차(01-1)와 파손 처리(02-1)를 완료 체크한 뒤에도 같은 업무를 반복해서 묻는다.
        "logs": [
            (17, 10, "01-1", "fact", "확정 물량은 몇 시에 내려받아요?",
             "오전 9시에 WMS에서 권역별 확정 물량을 내려받습니다."),
            (16, 14, "01-1", "fact", "1톤 차량에 몇 박스까지 실어요?",
             "1톤 기준 120박스가 적재 한도입니다."),
            (15, 11, "01", "procedure", "오후에 들어온 물량은 어떻게 배차해요?",
             "오후 추가분은 예비 차량으로 돌립니다. 오후 1시 이후 긴급 물량은 예비 차량 2대로 처리합니다."),
            (11, 10, "01-1", "procedure", "배차표에서 기사를 권역에 어떻게 넣어요?",
             "관제 시스템 배차 메뉴에서 기사를 권역에 끌어다 놓으면 됩니다. 저장하면 기사 앱으로 목록이 전송됩니다."),
            (10, 9, "01-1", "fact", "배차는 몇 시까지 끝내야 하나요?",
             "9시 40분까지 확정합니다. 늦어지면 첫 회차 출발이 밀려 오후 배송이 지연됩니다."),
            (9, 15, "02-1", "procedure", "파손 보고 들어오면 뭐부터 해요?",
             "사진을 확인하고 사고 유형을 파손으로 접수한 뒤, 30분 안에 고객에게 문자로 안내합니다."),
            (8, 11, "01-1", "procedure", "권역 물량을 차량 대수로 나누는 계산 다시 알려주세요",
             "권역별 확정 물량을 1톤 기준 120박스로 나눠 필요한 차량 대수를 구합니다."),
            (6, 14, "02-1", "judgment", "파손 금액이 32만 원이면 보고서 따로 써야 해요?",
             "30만 원을 넘으므로 보험 접수 대상입니다. 사고 보고서를 따로 작성해야 합니다."),
            (5, 10, "01-1", "procedure", "배차표 저장했는데 기사 앱에 안 떴어요. 순서가 맞나요?",
             "배차 메뉴에서 기사를 권역에 배치한 뒤 저장해야 기사 앱으로 전송됩니다. 저장 전에 화면을 벗어나면 반영되지 않습니다."),
            (4, 16, "02-1", "procedure", "재발송하기로 하면 어디로 넘겨요?",
             "재발송이면 당일 긴급 배차로 넘깁니다."),
            (3, 11, None, "fact", "기사님 연차는 누가 승인해요?", NO_ANSWER),
            (2, 10, "01-1", "procedure", "배차 확정하기 전에 확인할 게 뭐가 있죠?",
             "권역별 물량과 필요 차량 대수를 맞췄는지 확인하고, 9시 40분 전에 저장까지 끝내야 합니다."),
            (1, 15, "02-2", "judgment", "2시간 반 늦어지는데 쿠폰 줘야 해요?",
             "2시간 이상 지연은 쿠폰 지급 대상입니다."),
        ],
        "summaries": {
            "growth_curve": {
                1: "배차 기준 시간과 적재 한도처럼 사실을 확인하는 질문으로 시작해 절차 질문으로 옮겨가고 있습니다.",
                2: "절차 질문이 여전히 가장 많습니다. 한 번 설명된 순서를 다시 묻는 경우가 섞여 있어, 실제로 해보면서 막히는 지점이 있어 보입니다.",
            },
            "chapter_heatmap": {
                1: "배차 영역에 질문이 몰려 있습니다. 첫 업무로 맡은 영역입니다.",
                2: "배차 절차와 파손 사고 처리에 질문이 똑같이 몰려 있습니다. 둘 다 완료 체크한 업무라, 문서만으로는 손에 익지 않은 영역으로 보입니다.",
            },
            "gap_task": {
                1: "배차 절차를 읽고 배차표까지 완료로 체크했지만, 이후에도 같은 절차를 다시 묻는 질문이 이어졌습니다.",
                2: "배차표 작성과 파손 사고 처리 모두 완료로 체크했지만, 이후에도 같은 업무를 반복해서 묻고 있습니다. 체크는 했지만 아직 혼자 하기 어려운 상태일 수 있어 한 번 옆에서 같이 해보길 권합니다.",
            },
            "silence_risk": {
                1: "질문이 기간 내내 고르게 이어졌습니다.",
                2: "질문이 줄지 않고 이어지고 있어 침묵 위험 신호는 없습니다.",
            },
        },
    },
    {
        "key": "c",
        "company": "미래테크",
        "mentor": "최유진",
        "newcomer": "한승우",
        "label": "미래테크 플랫폼개발팀 인수인계서",
        "assigned_days_ago": 16,
        "chapters": [
            ("01", None, "배포",
             "운영 배포는 화요일과 목요일 오후 2시에만 한다. 금요일과 공휴일 전날에는 배포하지 않는다."),
            ("01-1", "01", "운영 배포 절차",
             "배포할 PR은 main에 머지되고 스테이징에서 30분 이상 문제가 없어야 한다.\n\n"
             "배포는 CI의 'deploy-prod' 워크플로를 수동 실행해서 시작한다. 실행 전에 배포 채널에 "
             "대상 PR 목록과 롤백 담당자를 적는다.\n\n"
             "배포 후 15분 동안 에러율 대시보드를 지켜보고, 이상이 없으면 채널에 완료를 남긴다."),
            ("01-2", "01", "롤백",
             "배포 후 에러율이 평소의 2배를 넘으면 원인을 찾기 전에 먼저 롤백한다.\n\n"
             "롤백은 'deploy-prod' 워크플로를 직전 태그로 다시 실행하면 된다. DB 마이그레이션이 포함된 "
             "배포는 코드만 되돌리면 안 되므로 반드시 사수에게 먼저 알린다."),
            ("02", None, "온콜",
             "온콜은 주 단위로 돌아가며, 첫 한 달은 사수와 함께 2인 1조로 선다."),
            ("02-1", "02", "장애 대응",
             "알림이 오면 5분 안에 장애 채널에 '확인 중'을 남긴다. 사용자 영향이 있으면 등급을 "
             "SEV2 이상으로 올린다.\n\n"
             "원인을 모르는 상태에서는 최근 배포부터 의심하고, 30분 안에 해결되지 않으면 사수를 호출한다.\n\n"
             "장애가 끝나면 48시간 안에 회고 문서를 쓴다."),
            ("02-2", "02", "알림 기준",
             "API p95 응답 시간이 1초를 넘거나 5xx 비율이 1%를 넘으면 알림이 온다. "
             "야간(23시~8시)에는 SEV2 이상만 전화로 호출된다."),
            ("03", None, "개발 환경",
             "로컬 개발은 docker compose로 DB와 캐시를 띄운다. 운영 DB 접근 권한은 입사 한 달 뒤에 신청할 수 있다."),
        ],
        "checklist": [
            ("개발 환경 세팅하기", "03", "manual", 14),
            ("운영 배포 절차 읽어보기", "01-1", "manual", 10),
            ("스테이징 배포 1회 참관하기", "01-1", "ai_draft", None),
            ("장애 대응 절차 읽어보기", "02-1", "manual", None),
            ("롤백 절차 확인하기", "01-2", "ai_draft", None),
        ],
        # 두 번째 리포트 기간(최근 7일)의 전반부에 질문이 몰리고 후반부에는 거의 없다.
        "logs": [
            (15, 10, "03", "fact", "로컬에서 DB는 어떻게 띄워요?",
             "docker compose로 DB와 캐시를 함께 띄웁니다."),
            (14, 15, "03", "fact", "운영 DB 접근 권한은 언제 받을 수 있어요?",
             "입사 한 달 뒤에 신청할 수 있습니다."),
            (13, 11, "01", "fact", "배포는 무슨 요일에 해요?",
             "화요일과 목요일 오후 2시에만 합니다. 금요일과 공휴일 전날에는 하지 않습니다."),
            (12, 14, "01-1", "procedure", "운영 배포는 어떻게 시작하나요?",
             "CI의 deploy-prod 워크플로를 수동 실행합니다. 실행 전에 배포 채널에 대상 PR과 롤백 담당자를 적습니다."),
            (11, 10, "01-1", "fact", "스테이징에서 얼마나 기다렸다가 배포해요?",
             "스테이징에서 30분 이상 문제가 없어야 합니다."),
            (10, 16, "02-2", "fact", "알림은 어떤 기준으로 와요?",
             "API p95 응답 시간이 1초를 넘거나 5xx 비율이 1%를 넘으면 알림이 옵니다."),
            (6.5, 10, "01-2", "procedure", "롤백은 어떻게 해요?",
             "deploy-prod 워크플로를 직전 태그로 다시 실행합니다. DB 마이그레이션이 포함된 배포는 먼저 사수에게 알립니다."),
            (6.2, 14, "02-1", "procedure", "알림 오면 제일 먼저 뭐 해요?",
             "5분 안에 장애 채널에 확인 중을 남기고, 사용자 영향이 있으면 SEV2 이상으로 올립니다."),
            (5.8, 11, "01-2", "judgment", "에러율이 평소의 1.5배면 롤백해야 하나요?",
             "문서 기준은 평소의 2배를 넘을 때 먼저 롤백하는 것입니다. 1.5배라면 대시보드를 계속 지켜보면서 사수와 상의하는 게 좋겠습니다."),
            (5.5, 15, "02-1", "judgment", "원인을 모르겠는데 사수를 언제 불러요?",
             "30분 안에 해결되지 않으면 사수를 호출합니다. 원인을 모를 때는 최근 배포부터 의심합니다."),
            (5.2, 10, None, "advanced", "배포 파이프라인 캐시는 어떻게 비워요?", NO_ANSWER),
            (4.8, 16, "02-1", "procedure", "장애 끝나면 회고는 언제까지 써요?",
             "장애가 끝나고 48시간 안에 회고 문서를 씁니다."),
            (1.5, 11, "01", "fact", "이번 주 배포 목요일 맞죠?",
             "배포는 화요일과 목요일 오후 2시에 합니다."),
        ],
        "summaries": {
            "growth_curve": {
                1: "개발 환경과 배포 일정처럼 사실을 확인하는 질문이 대부분이었습니다. 환경을 파악하는 단계로 보입니다.",
                2: "롤백 기준이나 사수 호출 시점처럼 판단이 필요한 질문이 나오기 시작했습니다. 온콜을 준비하는 흐름과 맞습니다.",
            },
            "chapter_heatmap": {
                1: "개발 환경과 배포 영역에 질문이 나뉘어 있습니다.",
                2: "장애 대응과 롤백에 질문이 몰려 있습니다. 온콜 투입을 앞두고 가장 부담을 느끼는 영역으로 보입니다.",
            },
            "gap_task": {
                1: "완료 체크한 뒤 같은 업무를 다시 묻는 항목은 없습니다.",
                2: "완료 체크한 항목과 이후 질문이 겹치지 않습니다.",
            },
            "silence_risk": {
                1: "질문이 기간 내내 이어졌습니다.",
                2: "기간 전반부에는 장애 대응과 롤백을 활발히 묻다가 후반부에는 질문이 거의 끊겼습니다. 스스로 해결하고 있을 수도 있지만 막혀서 멈춘 것일 수도 있어, 온콜 투입 전에 한 번 확인해보길 권합니다.",
            },
        },
    },
]


def wipe(db, key: str) -> None:
    """이 회사의 데모 행만 지운다. 데모가 아닌 데이터는 건드리지 않는다."""
    mentor_id, newcomer_id, document_id = f"demo-mentor-{key}", f"demo-newcomer-{key}", f"demo-document-{key}"

    db.query(ChatLogORM).filter(ChatLogORM.newcomer_id == newcomer_id).delete()
    db.query(ChecklistItemORM).filter(ChecklistItemORM.newcomer_id == newcomer_id).delete()
    db.query(AssignmentORM).filter(AssignmentORM.newcomer_id == newcomer_id).delete()
    db.query(DocumentChapterORM).filter(DocumentChapterORM.document_id == document_id).delete()
    db.query(DocumentMentorMapORM).filter(DocumentMentorMapORM.document_id == document_id).delete()

    report_ids = [
        r.report_id
        for r in db.query(AdaptationReportORM).filter(AdaptationReportORM.newcomer_id == newcomer_id)
    ]
    if report_ids:
        db.query(ReportSectionORM).filter(ReportSectionORM.report_id.in_(report_ids)).delete(
            synchronize_session=False
        )
        db.query(AdaptationReportORM).filter(AdaptationReportORM.report_id.in_(report_ids)).delete(
            synchronize_session=False
        )

    db.query(UserORM).filter(UserORM.user_id.in_([mentor_id, newcomer_id])).delete(
        synchronize_session=False
    )
    db.commit()


def seed_company(db, spec: dict) -> dict:
    key = spec["key"]
    mentor_id, newcomer_id, document_id = f"demo-mentor-{key}", f"demo-newcomer-{key}", f"demo-document-{key}"
    assigned_at = at(spec["assigned_days_ago"], hour=9)

    db.add_all(
        [
            UserORM(
                user_id=mentor_id,
                name=spec["mentor"],
                email=f"demo-mentor-{key}@handover.demo",
                password_hash=hash_password(DEMO_PASSWORD),
                role="mentor",
            ),
            UserORM(
                user_id=newcomer_id,
                name=spec["newcomer"],
                email=f"demo-newcomer-{key}@handover.demo",
                password_hash=hash_password(DEMO_PASSWORD),
                role="newcomer",
            ),
        ]
    )

    db.add(
        DocumentMentorMapORM(
            document_id=document_id,
            mentor_id=mentor_id,
            label=spec["label"],
            uploaded_at=assigned_at - timedelta(days=1),
        )
    )
    chapter_id = {ck: f"demo-{key}-{ck}" for ck, *_ in spec["chapters"]}
    for ck, parent, title, content in spec["chapters"]:
        db.add(
            DocumentChapterORM(
                chapter_id=chapter_id[ck],
                document_id=document_id,
                title=title,
                parent_id=chapter_id[parent] if parent else None,
                content=content,
            )
        )

    db.add(
        AssignmentORM(
            assignment_id=f"demo-assignment-{key}",
            newcomer_id=newcomer_id,
            mentor_id=mentor_id,
            document_id=document_id,
            assigned_at=assigned_at,
        )
    )

    checklist_rows = []
    for order, (title, ck, source, done_days) in enumerate(spec["checklist"], start=1):
        completed_at = at(done_days, hour=17) if done_days is not None else None
        db.add(
            ChecklistItemORM(
                item_id=str(uuid.uuid4()),
                newcomer_id=newcomer_id,
                chapter_id=chapter_id[ck] if ck else None,
                title=title,
                order=order,
                status="done" if completed_at else "pending",
                completed_at=completed_at,
                source=source,
            )
        )
        checklist_rows.append(
            {"title": title, "chapter_id": chapter_id[ck] if ck else None, "completed_at": completed_at}
        )

    log_rows = []
    for days_ago, hour, ck, qtype, question, answer in spec["logs"]:
        created_at = NOW - timedelta(days=days_ago)
        created_at = created_at.replace(hour=hour, minute=0)
        answered = ck is not None
        db.add(
            ChatLogORM(
                log_id=str(uuid.uuid4()),
                newcomer_id=newcomer_id,
                document_id=document_id,
                question=question,
                answer=answer,
                answered=answered,
                matched_chapter_id=chapter_id[ck] if ck else None,
                question_type=qtype,
                created_at=created_at,
            )
        )
        log_rows.append(
            {
                "question_type": qtype,
                "matched_chapter_id": chapter_id[ck] if ck else None,
                "answered": answered,
                "created_at": created_at,
            }
        )

    # 리포트 2건: 배정일~중간, 중간~오늘. 기간을 반씩 나눠야 두 리포트가 비슷한 양의 질문을
    # 나눠 갖는다 — 한쪽이 몇 건뿐이면 레이더가 거의 비어 보인다. 두 번째 리포트 화면에서
    # 첫 번째가 점선으로 겹쳐 그려진다.
    boundary = at(spec["assigned_days_ago"] / 2, hour=9)
    periods = [(1, assigned_at, boundary), (2, boundary, NOW - timedelta(hours=1))]
    for index, start, end in periods:
        logs_in = [log for log in log_rows if start <= log["created_at"] <= end]
        signals = {
            "growth_curve": _compute_growth_curve(logs_in),
            "chapter_heatmap": _compute_chapter_heatmap(logs_in),
            "gap_task": _compute_gap_task(checklist_rows, logs_in),
            "silence_risk": _compute_silence_risk(logs_in, start, end),
        }
        report_id = f"demo-report-{key}-{index}"
        db.add(
            AdaptationReportORM(
                report_id=report_id,
                newcomer_id=newcomer_id,
                period_start=start,
                period_end=end,
                generated_at=end,
            )
        )
        for signal_type, data in signals.items():
            db.add(
                ReportSectionORM(
                    section_id=str(uuid.uuid4()),
                    report_id=report_id,
                    signal_type=signal_type,
                    summary=spec["summaries"][signal_type][index],
                    data=data,
                )
            )

    db.commit()
    latest = {
        "gap_items": len(signals["gap_task"]["gap_items"]),
        "dropped_sharply": signals["silence_risk"].get("dropped_sharply"),
        "questions": signals["growth_curve"]["total"],
    }
    return {
        "chapters": len(spec["chapters"]),
        "checklist": len(spec["checklist"]),
        "logs": len(spec["logs"]),
        "latest": latest,
    }


def main() -> None:
    db = SessionLocal()
    try:
        for spec in COMPANIES:
            wipe(db, spec["key"])
            result = seed_company(db, spec)
            latest = result["latest"]
            print(
                f"[{spec['key']}] {spec['company']:<6} 업무 {result['chapters']}개 · "
                f"체크리스트 {result['checklist']}개 · 질문 {result['logs']}건 · 리포트 2건 "
                f"(최신: 질문 {latest['questions']}건, 불일치 {latest['gap_items']}건, "
                f"급감 {'예' if latest['dropped_sharply'] else '아니오'})"
            )
    finally:
        db.close()

    print()
    print(f"로그인: demo-mentor-a@handover.demo / {DEMO_PASSWORD}  (b, c 동일 규칙, 신입은 demo-newcomer-*)")
    print("주의: 임베딩이 없어 데모 신입이 새로 질문하면 답을 찾지 못합니다. (챗봇 시연에는 문서 재업로드 필요)")


if __name__ == "__main__":
    main()
