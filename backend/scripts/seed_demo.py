"""Demo data for the four demo companies (guidelines 1-8, 6-6).

기본 실행은 **점검만** 한다 — OpenAI를 부르지 않고 과금도 없다. 실제로 넣으려면 --execute를
붙인다.

    cd backend
    python scripts/seed_demo.py                     # 점검: 회사별 신호와 예상 OpenAI 호출 수 출력
    python scripts/seed_demo.py --only a            # 점검: 회사 한 곳만
    python scripts/seed_demo.py --execute --only a  # 실행: 한 곳만 실제로 넣기 (리허설용)
    python scripts/seed_demo.py --execute           # 실행: 네 곳 전부

실행 모드는 백엔드 서버가 떠 있어야 한다(기본 http://localhost:8000, --api로 변경).

── 무엇을 API로, 무엇을 DB에 직접 넣나 ────────────────────────────────
실제 서비스와 똑같이 동작해야 하는 것은 전부 API를 탄다.
  - 문서 업로드   POST /document/upload  → 챕터 파싱·청킹·임베딩이 실제 파이프라인 그대로
                                            (그래서 데모 신입이 새 질문을 해도 챗봇이 답한다)
  - 추가 신입 가입 POST /user/register
  - 배정          POST /assignment
  - 체크리스트    POST /checklist         → 배정 문서 챕터 검증까지 그대로
  - 리포트        POST /report/generate   → 신호는 서버가 계산하고 요약은 LLM이 쓴다

API로는 만들 수 없어서 DB에 직접 넣는 것.
  - 고정 ID 계정 8개  : 가입 API는 user_id를 무작위 UUID로만 만든다. DEMO_USER_IDS(rate limit
                        예외)와 맞추려면 demo-mentor-a 같은 고정값이어야 한다 (guidelines 6-6).
  - 과거 시각          : API는 배정일·완료 시각·질문 시각을 "지금"으로 찍는다. 몇 주에 걸친
                        적응 과정을 보여주려면 이 시각들을 과거로 되돌려야 한다.
  - 챗로그             : /chat/ask로 쌓으면 질문당 OpenAI 3회이고, LLM 분류에 따라 회사별로
                        보여주려는 신호가 나온다는 보장이 없다. 리포트는 이 챗로그를 서버가
                        그대로 읽어 계산하므로 신호 값은 실제 계산 결과다. (조장 확인, 9/14)

── 회사 구성 ───────────────────────────────────────────────────────────
네 회사 모두 같은 틀이다: 사수 1명 + 신입 3명(대표 1명은 데모 로그인용 고정 ID, 추가 2명은 일반
가입). 신입 유형별 질문 흐름은 아래 ARCHETYPES에 회사와 무관하게 한 번만 정의하고, 회사마다
질문 문장만 바꿔 끼운다 — 그래야 네 회사의 스타일이 같다.

  대표 신입   a 순조로운 적응 · b 완료한 업무를 반복해서 물음 · c 후반부 질문 급감 · d 질문이 깊어짐
  추가 신입 1 배정 1주차 (아직 판단하기 이른 단계)
  추가 신입 2 한 영역에만 질문이 몰림

문서는 frontend/public/demo-files/{회사}-handover.md를 올린다 — 데모 페이지에서 내려받는 파일과
같은 원본이다. 모든 원본은 "# 대분류 / ## 소분류" 9개 업무 구조로 되어 있고, 질문 흐름은 그
순서(역할 T1 S11 S12 T2 S21 S22 T3 S31 S32)를 기준으로 짠다.
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND, ".env"))

DEMO_FILES = os.path.join(BACKEND, "..", "frontend", "public", "demo-files")
DEMO_PASSWORD = "demo-handover-2026"  # frontend/src/pages/DemoPage.jsx 와 같아야 한다
NO_ANSWER = "문서에 없는 내용이니 담당자에게 문의하세요."  # routers/chat.py NO_ANSWER_MESSAGE

ROLES = ["T1", "S11", "S12", "T2", "S21", "S22", "T3", "S31", "S32"]

# ── 신입 유형 (회사와 무관) ──────────────────────────────────────────
# assigned : 배정 후 경과 일수(오늘 0시 기준)
# done     : CHECKLIST_SHAPE 순서대로 완료한 날(며칠 전, 17시) — None이면 미완료
# phases   : 질문 흐름을 구간으로 적는다. 구간마다 (며칠 전 ~ 며칠 전, 하루 질문 수, 업무 순서,
#            질문 유형 순서)를 두고, 평일만 돌면서 질문을 만든다. 주말에 질문이 없는 것은 정상이고,
#            리포트 화면도 주말을 옅게 칠해서 "끊긴 날"과 구분한다.
#            업무·유형 목록은 순서대로 돌려 쓰므로, 비율은 목록에 같은 값을 여러 번 적어 맞춘다.
#            miss=n을 주면 그 구간에 "문서에 없어 답을 못 찾은 질문"을 n건 섞는다.

CHECKLIST_SHAPE = [("read", "S11"), ("do", "S11"), ("read", "S21"), ("do", "S21"), ("read", "S31")]

HOURS = [10, 11, 14, 16, 17]  # 하루에 여러 건이면 이 시각들로 흩뜨린다


def phase(start, end, per_day, roles, mix, miss=0):
    """per_day는 숫자 하나 또는 요일마다 돌려 쓸 목록(예: [2, 3, 1])이다 — 매일 같은 건수면
    리포트 달력이 한 가지 색으로만 채워져서 활발한 날과 뜸한 날이 구분되지 않는다."""
    counts = per_day if isinstance(per_day, list) else [per_day]
    return {"start": start, "end": end, "per_day": counts, "roles": roles, "mix": mix, "miss": miss}


ARCHETYPES = {
    # 순조로운 적응 — 업무를 고르게 묻고, 완료한 업무는 다시 묻지 않고, 뒤로 갈수록 판단 질문이 는다
    "steady": {
        "assigned": 21,
        "done": [18, 14, 9, 4, None],
        "phases": [
            phase(20, 15, [4, 2, 1, 3, 2], ["S11", "S11", "T1", "S12"], ["fact", "fact", "procedure"]),
            phase(14, 8, [2, 0, 3, 1, 4, 2], ["S21", "S22", "S21", "T2", "S12"], ["procedure", "judgment", "procedure"]),
            phase(7, 1, [3, 1, 2, 0, 4], ["S31", "S32", "S22", "T3", "S12"], ["judgment", "judgment", "advanced"]),
        ],
    },
    # 완료한 업무를 반복해서 물음 — 읽고 실습까지 체크한 업무를 이후에도 계속 묻는다
    "repeat": {
        "assigned": 18,
        "done": [16, 13, 12, None, None],
        "phases": [
            phase(17, 14, [4, 2, 3, 1], ["S11", "S11", "T1"], ["fact", "fact", "procedure"]),
            phase(13, 8, [3, 1, 4, 2, 0], ["S11", "S21", "S11", "S12"], ["procedure", "fact", "procedure"]),
            phase(7, 1, [2, 4, 1, 3, 2], ["S11", "S21", "S11", "S22"], ["procedure", "procedure", "judgment"]),
        ],
    },
    # 도중에 손을 놓음 — 앞쪽에는 매일 들어오다가 어느 날부터 질문도 체크리스트도 멈춘다
    "silence": {
        "assigned": 18,
        "done": [17, 15, None, None, None],
        "phases": [
            phase(17, 14, [5, 3, 6, 2], ["T3", "S31", "T1", "S12", "S32", "S21", "S22"], ["fact", "fact", "procedure"], miss=2),
        ],
    },
    # 질문이 깊어지는 성장 — 사실 확인에서 절차로, 다시 판단·심화로 옮겨간다
    "growth": {
        "assigned": 20,
        "done": [17, 12, 8, 3, None],
        "phases": [
            phase(19, 15, [3, 1, 4, 2], ["S11", "T1", "S11", "S12"], ["fact", "fact", "procedure"]),
            phase(14, 8, [2, 4, 1, 0, 3], ["S21", "S12", "S22", "S21"], ["procedure", "procedure", "judgment"]),
            phase(7, 1, [4, 2, 1, 3, 2], ["S22", "S31", "S32", "T3", "S12"], ["judgment", "advanced", "advanced"]),
        ],
    },
    # 배정 1주차 — 아직 판단하기 이른 단계
    "early": {
        "assigned": 5,
        "done": [1, None, None, None, None],
        "phases": [phase(4, 1, [4, 2, 5, 3], ["S11", "T1", "S11", "S12", "S21"], ["fact", "fact", "procedure"])],
    },
    # 한 영역에만 질문이 몰림 — 둘째 대분류 안에서만 맴돈다
    "narrow": {
        "assigned": 15,
        "done": [12, 8, None, None, None],
        "phases": [
            phase(14, 8, [3, 2, 0, 4, 1], ["S21", "S21", "S22", "T2"], ["fact", "procedure", "procedure"]),
            phase(7, 1, [2, 5, 1, 2, 3], ["S21", "S22", "S21"], ["procedure", "judgment", "procedure"], miss=2),
        ],
    },
}

# ── 회사 (문장만 다르다) ─────────────────────────────────────────────
# questions: 역할 → {질문 유형: [질문, ...]}  같은 유형이 여러 번 쓰이면 순서대로 꺼낸다.
# practice: "do" 체크리스트 항목의 역할별 제목

COMPANIES = [
    {
        "key": "a",
        "company": "새싹커머스",
        "mentor": "김지훈",
        "newcomers": [("박서연", "steady"), ("오하늘", "early"), ("윤재민", "narrow")],
        "label": "새싹커머스 상품운영팀 인수인계서",
        "practice": {"S11": "테스트 상품 1건 등록해보기", "S21": "이번 달 정산 예정표 확인하기"},
        "questions": {
            "T1": {"fact": ["등록하고 바로 판매되나요?"], "procedure": ["행사 상품은 언제까지 등록해야 해요?"]},
            "S11": {
                "fact": ["상품 등록은 어디서 하나요?", "대표 이미지 크기 기준이 있나요?", "검수 반려 사유는 어디서 봐요?"],
                "procedure": ["옵션 있는 상품은 재고를 어떻게 넣어요?", "카테고리를 잘못 골랐으면 어떻게 고쳐요?",
                              "옵션 조합 만드는 순서를 다시 알려주세요", "검수 대기에서 판매 중으로 바꾸려면 뭘 해야 하죠?",
                              "등록 저장했는데 목록에 안 보여요. 순서가 맞나요?"],
            },
            "S12": {"fact": ["가격을 바꾸면 바로 반영되나요?", "판매 중지하면 주문은 어떻게 돼요?"],
                    "procedure": ["상품명을 바꾸면 다시 검수받나요?", "재고를 수정하려면 어디로 들어가요?"],
                    "judgment": ["행사 중인 상품 이름에 오타가 있으면 고쳐도 되나요?",
                                 "가격을 잘못 올린 걸 발견하면 바로 내려도 되나요?",
                                 "판매 중지한 상품을 다시 살릴 때 뭘 확인해요?"]},
            "T2": {"fact": ["정산은 누가 확정해요?"],
                   "procedure": ["정산 관련 문의는 어디로 넣어요?", "정산 일정은 매달 같나요?",
                                 "정산 확정 전에 우리가 확인할 게 있나요?"],
                   "advanced": ["정산 예정표 금액이 안 맞으면 누구한테 먼저 연락해요?"]},
            "S21": {"fact": ["정산 마감이 언제예요?", "정산 예정표는 언제 와요?"],
                    "procedure": ["정산 예정표 금액이 다르면 어떻게 이의를 올려요?", "마감 이후 취소된 건은 어떻게 처리돼요?",
                                  "정산 예정표에서 확인할 항목이 뭐예요?", "정산 예정표는 어디서 내려받아요?",
                                  "정산 금액이 맞는지 어떻게 대조해요?", "이의 제기는 어느 화면에서 넣어요?",
                                  "마감 전에 챙겨야 할 서류가 있나요?", "지난달 정산 내역은 어디서 봐요?",
                                  "정산 담당자에게는 어떻게 연락해요?", "입금액이 예정표와 다르면 어디에 적어요?", "마감 후 정정은 어떻게 올려요?"],
                    "judgment": ["말일이 휴일이면 마감이 앞당겨지나요?", "이의 제기가 늦어지면 어떻게 되나요?"]},
            "S22": {"fact": ["정산 예외 시트는 어디에 있어요?"],
                    "procedure": ["부분 취소된 주문은 정산을 어떻게 처리하나요?", "정산 예외 시트는 어떻게 작성해요?",
                                  "교환으로 금액이 바뀐 건은 어디에 적어요?"],
                    "judgment": ["마감 이틀 전에 예외 요청이 오면 받아도 되나요?", "예외 건이 많으면 먼저 공유해야 하나요?",
                                 "예외 처리 금액이 크면 누구 확인을 받아요?"],
                    "advanced": ["예외 처리 기한을 놓친 건은 다음 달에 어떻게 반영돼요?"]},
            "T3": {"fact": ["반품은 누가 접수해요?"],
                   "judgment": ["반품 사유가 애매하면 어느 쪽으로 처리해요?"],
                   "advanced": ["반품이 자주 들어오는 상품은 따로 보고해야 하나요?"]},
            "S31": {"fact": ["환불 버튼은 언제 활성화돼요?"],
                    "procedure": ["반품 접수는 어느 화면에서 해요?", "회수 완료는 어떻게 확인해요?"],
                    "advanced": ["반품이 잦은 상품은 상세페이지를 고쳐야 할까요?"],
                    "judgment": ["고객이 색이 다르다고 반품하면 배송비 차감해야 하나요?",
                                 "포장을 뜯은 상품도 반품 받아야 하나요?"]},
            "S32": {"fact": ["다른 상품으로도 교환되나요?"], "procedure": ["교환 상품 재고가 없으면 어떻게 해요?"],
                    "judgment": ["교환 요청 옵션이 품절이면 비슷한 옵션으로 보내도 되나요?",
                                 "교환 배송비는 누가 부담해요?"],
                    "advanced": ["교환이 반복되는 옵션은 등록 정보를 고쳐야 할까요?"]},
        },
    },
    {
        "key": "b",
        "company": "한빛물류",
        "mentor": "이도현",
        "newcomers": [("정민재", "repeat"), ("강다은", "early"), ("임준호", "narrow")],
        "label": "한빛물류 배송관제팀 인수인계서",
        "practice": {"S11": "배차표 1회 작성해보기", "S21": "파손 접수 모의 처리해보기"},
        "questions": {
            "T1": {"fact": ["배차는 몇 시 물량 기준이에요?"],
                   "procedure": ["오후에 들어온 물량은 어떻게 배차해요?", "배차 결과는 누구에게 공유해요?",
                                 "배차표 양식은 어디 있어요?"]},
            "S11": {
                "fact": ["확정 물량은 몇 시에 내려받아요?", "1톤 차량에 몇 박스까지 실어요?", "배차는 몇 시까지 끝내야 하나요?",
                         "권역은 몇 개로 나뉘어 있어요?", "배차표는 기사 앱에 언제 반영돼요?"],
                "judgment": ["물량이 애매하게 남으면 용차를 부를까요, 나눠 실을까요?",
                             "기사 한 명이 결근하면 어느 권역부터 조정해요?"],
                "procedure": ["배차표에서 기사를 권역에 어떻게 넣어요?", "권역 물량을 차량 대수로 나누는 계산 다시 알려주세요",
                              "배차표 저장했는데 기사 앱에 안 떴어요. 순서가 맞나요?", "배차 확정하기 전에 확인할 게 뭐가 있죠?",
                              "배차표 저장 순서를 한 번만 더 알려주세요", "기사 배정은 어디서 바꿔요?",
                              "물량이 갑자기 늘면 배차표를 어떻게 고쳐요?", "배차표를 다시 보내려면 어떻게 해요?"],
            },
            "S12": {"fact": ["예비 차량은 몇 대예요?"], "procedure": ["용차는 어떻게 요청해요?"]},
            "T2": {"fact": ["사고 보고는 누가 먼저 해요?"], "procedure": ["사고 접수 후 고객 안내는 언제까지 해요?"]},
            "S21": {"fact": ["파손 보고가 들어오면 제일 먼저 뭘 확인해요?", "파손 사고 보험 기준 금액이 얼마예요?"],
                    "procedure": ["파손 보고 들어오면 뭐부터 해요?", "재발송하기로 하면 어디로 넘겨요?",
                                  "파손 접수 순서 다시 알려주세요", "고객 안내 문자는 어디서 보내요?",
                                  "재발송 긴급 배차는 어떻게 넘겨요?", "사고 사진은 어디에 올려요?",
                                  "보험 접수는 어떤 서류가 필요해요?", "사고 내역은 어느 시트에 적어요?", "재발송 진행 상황은 어디서 봐요?",
                                  "고객 보상은 누가 결정해요?"],
                    "judgment": ["파손 금액이 32만 원이면 보고서 따로 써야 해요?", "고객이 재발송도 환불도 싫다고 하면요?"]},
            "S22": {"fact": ["지연 기준 시간이 몇 시간이에요?"],
                    "procedure": ["지연 안내는 언제 연락해요?", "예상 도착 시간은 어떻게 계산해요?",
                                  "지연 쿠폰은 어디서 발급해요?", "지연 사유는 어디에 기록해요?"],
                    "judgment": ["2시간 반 늦어지는데 쿠폰 줘야 해요?", "기사 연락이 안 되면 고객에게 뭐라고 안내해요?",
                                 "고객이 재배송 대신 환불을 원하면 어떻게 해요?"]},
            "T3": {"fact": ["마감 보고는 몇 시에 올려요?"], "advanced": ["완료율이 계속 낮으면 따로 보고해야 하나요?"]},
            "S31": {"fact": ["완료율 기준이 몇 퍼센트예요?"], "judgment": ["완료율이 94%면 원인을 적어야 해요?"]},
            "S32": {"fact": ["주간 사고 집계는 언제 보내요?"],
                    "judgment": ["같은 기사에게 사고가 두 번 나면 따로 표시하나요?"]},
        },
    },
    {
        "key": "c",
        "company": "미래테크",
        "mentor": "최유진",
        "newcomers": [("한승우", "silence"), ("서지안", "early"), ("노태윤", "narrow")],
        "label": "미래테크 플랫폼개발팀 인수인계서",
        "practice": {"S11": "스테이징 배포 1회 참관하기", "S21": "장애 대응 모의 훈련 참여하기"},
        "questions": {
            "T1": {"fact": ["배포는 무슨 요일에 해요?", "이번 주 배포 목요일 맞죠?"], "procedure": ["배포 전에 채널에 뭘 적어요?"]},
            "S11": {"fact": ["스테이징에서 얼마나 기다렸다가 배포해요?", "배포 후 얼마나 지켜봐요?", "deploy-prod는 누가 실행해요?"],
                    "procedure": ["운영 배포는 어떻게 시작하나요?", "배포 채널에 PR 목록은 어떻게 적어요?",
                                  "배포 완료는 어떻게 남겨요?", "스테이징 확인은 어떤 대시보드로 해요?",
                                  "배포 순서를 다시 한 번 알려주세요"]},
            "S12": {"fact": ["롤백 기준이 뭐예요?", "롤백하면 어느 버전으로 돌아가요?"],
                    "procedure": ["롤백은 어떻게 해요?", "롤백 후에는 무엇을 확인해요?"],
                    "judgment": ["에러율이 평소의 1.5배면 롤백해야 하나요?"]},
            "T2": {"fact": ["온콜은 얼마나 자주 서요?"], "procedure": ["온콜 교대는 어떻게 해요?"]},
            "S21": {"fact": ["장애 등급은 어떻게 나눠요?", "회고 문서는 며칠 안에 써야 해요?"],
                    "procedure": ["알림 오면 제일 먼저 뭐 해요?", "장애 끝나면 회고는 언제까지 써요?", "장애 채널에는 뭐라고 남겨요?",
                                  "SEV2로 올리는 기준을 다시 알려주세요", "회고 문서 양식은 어디 있어요?",
                                  "장애 알림은 어디로 오나요?", "온콜 교대 시간은 어떻게 기록해요?",
                                  "장애 상황은 누구에게 먼저 알려요?", "복구 후 확인해야 할 지표가 뭐예요?",
                                  "장애 공지는 어느 채널에 올려요?"],
                    "judgment": ["원인을 모르겠는데 사수를 언제 불러요?", "최근 배포가 없는데 장애가 나면 어디부터 봐요?"]},
            "S22": {"fact": ["알림은 어떤 기준으로 와요?", "야간 호출 기준이 어떻게 돼요?"],
                    "procedure": ["야간 알림은 어떻게 받아요?", "5xx 비율 알림이 오면 어디부터 확인해요?",
                                  "알림 기준 값은 어디서 확인해요?", "알림을 잠시 끄려면 어떻게 해요?"],
                    "judgment": ["p95가 0.9초에서 오래 머물면 미리 알려야 하나요?",
                                 "알림이 반복해서 울리면 기준을 조정해도 되나요?",
                                 "새벽에 오는 알림은 아침에 봐도 될까요?"],
                    "advanced": ["알림 기준을 서비스별로 다르게 둘 수 있을까요?"]},
            "T3": {"fact": ["로컬에서 DB는 어떻게 띄워요?", "개발 환경 준비는 언제까지 끝내야 해요?"],
                   "advanced": ["개발 환경 구성을 문서로 자동화해도 될까요?"]},
            "S31": {"fact": ["시드 데이터는 어떻게 넣어요?"],
                    "procedure": ["로컬 환경은 어떤 순서로 세팅해요?", "docker compose는 어떤 명령으로 띄워요?"],
                    "judgment": ["운영 데이터 일부만 로컬로 받아도 되나요?"]},
            "S32": {"fact": ["운영 DB 접근 권한은 언제 받을 수 있어요?"],
                    "procedure": ["스테이징 접근 권한은 어떻게 신청해요?"],
                    "advanced": ["권한 신청 절차를 입사 체크리스트에 넣으면 어떨까요?"]},
        },
    },
    {
        "key": "d",
        "company": "그린푸드",
        "mentor": "한소영",
        "newcomers": [("김도윤", "growth"), ("이수아", "early"), ("최민서", "narrow")],
        "label": "그린푸드 인사팀 인수인계서",
        "practice": {"S11": "채용 공고 초안 작성해보기", "S21": "이번 달 급여 마감 일정 정리하기"},
        "questions": {
            "T1": {"fact": ["채용은 어디서부터 인사팀이 맡아요?"], "procedure": ["현업 요청이 들어오면 제일 먼저 뭘 해요?"]},
            "S11": {"fact": ["공고는 어디에 올려요?", "공고 마감일은 며칠 뒤로 잡아요?", "인력 요청서는 누가 승인해요?"],
                    "procedure": ["채용 공고는 어떤 순서로 만들어요?", "외부 채용 사이트에는 어떻게 올려요?",
                                  "공고 문구는 누가 검토해요?", "승인 확인은 어디서 해요?", "공고 수정은 어떻게 해요?"]},
            "S12": {"fact": ["면접관은 몇 명이 들어가요?", "면접 평가표는 언제까지 받아요?"],
                    "procedure": ["면접 일정은 언제까지 안내해요?", "면접 결과는 어떻게 통보해요?",
                                  "면접 일정 변경 요청은 어떻게 처리해요?"],
                    "advanced": ["면접 일정이 자주 밀리는 부서는 어떻게 개선할까요?"],
                    "judgment": ["면접관 평가가 크게 엇갈리면 어떻게 정리해요?", "평가표가 하루 늦게 오면 합격 결정을 미뤄야 하나요?",
                                 "지원자가 일정을 계속 미루면 어떻게 하죠?"]},
            "T2": {"fact": ["급여일이 언제예요?"], "procedure": ["급여 계산은 어떤 순서로 해요?"]},
            "S21": {"fact": ["근태 마감은 며칠이에요?", "급여 대장은 며칠에 확정해요?"],
                    "procedure": ["급여 대장은 누구 확인을 받아요?", "20일 이후 수당 변경은 어떻게 처리해요?",
                                  "급여 대장 확정 순서를 다시 알려주세요", "근태 마감 누락자는 어떻게 챙겨요?",
                                  "급여 마감 일정표는 어디서 봐요?", "근태 자료는 어디서 받아요?",
                                  "급여 대장은 어떤 양식으로 만들어요?", "수당 항목은 어디에 입력해요?",
                                  "확정 전에 누구에게 검토를 받아요?", "지난달 급여 대장은 어디서 봐요?"],
                    "judgment": ["21일에 들어온 수당 누락은 이번 달에 넣어도 되나요?", "재무팀장이 부재면 확정을 미뤄야 하나요?"]},
            "S22": {"fact": ["급여 문의는 보통 며칠에 몰려요?"],
                    "procedure": ["급여 문의는 어디로 받아요?", "계산 오류 차액은 어떻게 지급해요?",
                                  "급여 명세서 재발급은 어떻게 해요?", "문의 내역은 어디에 기록해요?"],
                    "judgment": ["메신저로 급여 문의가 오면 어떻게 답해요?", "오류 금액이 작으면 다음 달에 반영해도 되나요?",
                                 "본인이 아닌 사람이 급여를 물어보면 어떻게 하죠?"],
                    "advanced": ["자주 오는 급여 문의를 FAQ로 만들어도 될까요?"]},
            "T3": {"fact": ["근태 관리는 어떤 규정을 따라요?"],
                   "judgment": ["규정과 관행이 다르면 어느 쪽을 따라요?"],
                   "advanced": ["노무 이슈가 생기면 외부 노무사와 언제 상의해요?"]},
            "S31": {"fact": ["연차 촉진 안내는 언제 보내요?"], "judgment": ["부서장 승인 없이 올라온 연차는 반려해야 하나요?"],
                    "advanced": ["연차 사용률이 낮은 부서는 촉진 안내를 따로 해야 할까요?"]},
            "S32": {"fact": ["퇴직금은 며칠 안에 정산해요?"],
                    "procedure": ["육아휴직 안내문은 어디 있어요?", "휴직 신청서는 어디에 보관해요?"],
                    "judgment": ["휴직 시작일이 급하게 당겨지면 어떻게 처리해요?"],
                    "advanced": ["퇴직 확정이 늦게 공유되는 부서는 어떻게 개선할까요?",
                                 "휴직 관련 문의를 안내문으로 정리해두면 어떨까요?"]},
        },
    },
]

EXTRA_EMAIL = "demo-extra-{key}{n}@handover.demo"


# ── 공통 ─────────────────────────────────────────────────────────────

def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# 기준 시각을 오늘 0시(UTC)로 고정한다. 실행 시각을 기준으로 잡으면 몇 시에 돌리느냐에 따라
# 질문 하나가 리포트 기간의 앞/뒤 절반을 넘나들어 신호가 바뀐다.
NOW = utcnow_naive().replace(hour=0, minute=0, second=0, microsecond=0)


# 서버는 UTC로 저장하고 화면은 보는 사람의 시간대로 보여준다. 시각을 UTC 기준으로 잡으면
# 한국에서 볼 때 오후 질문이 다음 날 새벽으로 밀려서, 리포트 달력에 주말 활동처럼 찍힌다.
# 그래서 hour는 한국 시간으로 받고 UTC로 바꿔 저장한다 (NOW = UTC 자정 = 한국 오전 9시).
KST_OFFSET = 9


def at(days_ago: float, hour_kst: int) -> datetime:
    return NOW - timedelta(days=days_ago) + timedelta(hours=hour_kst - KST_OFFSET)


def at_workday(days_ago: int, hour: int) -> datetime:
    """주말이면 직전 평일로 당긴다 (한국 시간 기준 요일) — 질문은 평일에만 넣는데 체크리스트 완료만 토·일에 찍히면
    리포트 달력에서 주말에만 활동한 날처럼 보인다."""
    while (NOW - timedelta(days=days_ago)).weekday() >= 5:
        days_ago += 1
    return at(days_ago, hour)


def parse_file(path):
    from routers.document import _parse_chapters_from_text

    with open(path, encoding="utf-8") as f:
        text = f.read()
    return _parse_chapters_from_text(text, fallback_title=os.path.basename(path))


def best_sentence(content: str, question: str) -> str:
    """질문과 두 글자 조각이 가장 많이 겹치는 본문 문장 — 같은 업무 질문마다 같은 답이 반복되지 않게."""
    sentences = [part.strip() + "다." for part in content.replace("\n", " ").split("다.") if part.strip()]

    def grams(text):
        text = text.replace(" ", "")
        return {text[i:i + 2] for i in range(len(text) - 1)}

    wanted = grams(question)
    return max(sentences, key=lambda sentence: len(wanted & grams(sentence)))


def build_logs(arch, take, by_role):
    """구간(phases)을 평일 단위로 풀어서 질문 로그를 만든다."""
    logs = []
    for ph in arch["phases"]:
        role_cycle, mix_cycle, misses, day_index = 0, 0, ph["miss"], 0
        for days_ago in range(ph["start"], ph["end"] - 1, -1):
            when = NOW - timedelta(days=days_ago)  # 한국 시간 기준 날짜
            if when.weekday() >= 5:  # 주말엔 묻지 않는다
                continue
            per_day = ph["per_day"][day_index % len(ph["per_day"])]
            day_index += 1
            for i in range(per_day):
                hour = HOURS[i % len(HOURS)]
                if misses and i == per_day - 1 and days_ago % 3 == 0:
                    misses -= 1
                    logs.append({
                        "created_at": at(days_ago, hour), "chapter_title": None, "question_type": "fact",
                        "question": MISSING_QUESTIONS[misses % len(MISSING_QUESTIONS)],
                        "answer": NO_ANSWER, "answered": False,
                    })
                    continue
                role = ph["roles"][role_cycle % len(ph["roles"])]
                qtype = ph["mix"][mix_cycle % len(ph["mix"])]
                role_cycle += 1
                mix_cycle += 1
                ch = by_role[role]
                question = take(role, qtype)
                logs.append({
                    "created_at": at(days_ago, hour),
                    "chapter_title": ch["title"],
                    "question_type": qtype,
                    "question": question,
                    "answer": f"인수인계서 '{ch['title']}'에 따르면, {best_sentence(ch['content'], question)}",
                    "answered": True,
                })
    return sorted(logs, key=lambda log: log["created_at"])


# 문서에 없어서 답을 못 찾는 질문 — 어느 회사에나 있을 법한 사내 일반 문의로 둔다.
MISSING_QUESTIONS = [
    "사내 복지 포인트는 어디서 신청해요?",
    "연차 쓸 때 결재선이 어떻게 되나요?",
    "법인카드 영수증은 어디에 올려요?",
    "사내 메신저 알림은 어떻게 꺼요?",
]


def build_plan(spec):
    """회사 한 곳의 신입별 계획(체크리스트·질문·기간)을 역할 → 챕터 제목으로 풀어 만든다."""
    chapters = parse_file(os.path.join(DEMO_FILES, f"{spec['key']}-handover.md"))
    assert len(chapters) == len(ROLES), f"{spec['key']}: 업무 {len(chapters)}개 (9개여야 함)"
    by_role = dict(zip(ROLES, chapters))

    plans = []
    for index, (name, archetype_key) in enumerate(spec["newcomers"]):
        arch = ARCHETYPES[archetype_key]
        pools = {r: {t: list(qs) for t, qs in spec["questions"].get(r, {}).items()} for r in ROLES}

        def take(role, qtype, pools=pools):
            pool = pools[role]
            if pool.get(qtype):
                return pool[qtype].pop(0)
            print(f"  ! {spec['key']} {name}: {role} {qtype} 질문 문장이 부족해 다른 유형 문장을 씀", file=sys.stderr)
            for other in pool.values():  # 같은 유형 질문이 떨어지면 다른 유형 문장이라도 쓴다
                if other:
                    return other.pop(0)
            return f"{by_role[role]['title']} 관련해서 한 번 더 여쭤봐도 될까요?"

        checklist = []
        for (kind, role), done_days in zip(CHECKLIST_SHAPE, arch["done"]):
            title = f"{by_role[role]['title']} 읽어보기" if kind == "read" else spec["practice"][role]
            checklist.append({
                "title": title,
                "chapter_title": by_role[role]["title"],
                "source": "manual" if kind == "read" else "ai_draft",
                "completed_at": at_workday(done_days, 17) if done_days is not None else None,
            })

        logs = build_logs(arch, take, by_role)

        plans.append({
            "name": name,
            "archetype": archetype_key,
            "fixed_id": f"demo-newcomer-{spec['key']}" if index == 0 else None,
            "email": (f"demo-newcomer-{spec['key']}@handover.demo" if index == 0
                      else EXTRA_EMAIL.format(key=spec["key"], n=index)),
            "assigned_at": at(arch["assigned"], 9),
            "period_start": at(arch["assigned"], 9),
            "period_end": NOW,
            "checklist": checklist,
            "logs": logs,
        })
    return chapters, plans


def iso(d):
    """오프셋 없는 UTC 문자열 — 서버가 DB에 쓰는 naive UTC와 같은 형태."""
    return d.strftime("%Y-%m-%dT%H:%M:%S") if d else None


# ── 점검 모드 (과금 없음) ─────────────────────────────────────────────

def dry_run(companies, out_path):
    """서버의 신호 계산 함수로 리포트 data를 미리 만들어본다. OpenAI·DB·서버 모두 쓰지 않는다."""
    from routers.report import (
        _compute_chapter_heatmap,
        _compute_gap_task,
        _compute_growth_curve,
        _compute_silence_risk,
    )

    exported = []
    embed_calls = llm_calls = 0
    for spec in companies:
        chapters, plans = build_plan(spec)
        # 점검용 가짜 chapter_id — 실제 업로드에서는 서버가 발급한다
        ids = {ch["title"]: f"dry-{spec['key']}-{i:02d}" for i, ch in enumerate(chapters)}
        embed_calls += len(chapters)
        print(f"\n[{spec['key']}] {spec['company']} — 사수 {spec['mentor']}, 업무 {len(chapters)}개")
        for plan in plans:
            llm_calls += 4
            logs = [
                {"question_type": log["question_type"], "answered": log["answered"], "created_at": log["created_at"],
                 "matched_chapter_id": ids.get(log["chapter_title"])}
                for log in plan["logs"] if plan["period_start"] <= log["created_at"] <= plan["period_end"]
            ]
            items = [{"title": c["title"], "chapter_id": ids[c["chapter_title"]], "completed_at": c["completed_at"]}
                     for c in plan["checklist"]]
            sections = {
                "growth_curve": _compute_growth_curve(logs),
                "chapter_heatmap": _compute_chapter_heatmap(logs),
                "gap_task": _compute_gap_task(items, logs),
                "silence_risk": _compute_silence_risk(logs, plan["period_start"], plan["period_end"]),
            }
            gap = sections["gap_task"]["gap_items"]
            si = sections["silence_risk"]
            print(f"  {plan['name']:<4} {plan['archetype']:<8} 질문 {len(plan['logs']):>2} · 완료 "
                  f"{sum(1 for c in plan['checklist'] if c['completed_at'])}/5 · 반복 "
                  f"{[g['question_count_after_complete'] for g in gap]} · 흐름 "
                  f"{si.get('first_half_questions', '-')}→{si.get('second_half_questions', '-')}"
                  f"{' 급감' if si.get('dropped_sharply') else ''}")

            exported.append({
                "company": spec["company"], "name": plan["name"], "archetype": plan["archetype"],
                "assignedAt": iso(plan["assigned_at"]),
                "report": {
                    "period_start": iso(plan["period_start"]), "period_end": iso(plan["period_end"]),
                    "sections": [{"signal_type": k, "summary": "", "data": v} for k, v in sections.items()],
                },
                "chatTimes": [iso(log["created_at"]) for log in plan["logs"]],
                "chapters": [{"chapter_id": ids[ch["title"]], "title": ch["title"], "parent_id": None}
                             for ch in chapters],
                "checklist": [{"title": c["title"], "chapter_id": ids[c["chapter_title"]],
                               "status": "done" if c["completed_at"] else "pending",
                               "completed_at": iso(c["completed_at"]), "order": i + 1}
                              for i, c in enumerate(plan["checklist"])],
            })

    print(f"\n예상 OpenAI 호출: 임베딩 {embed_calls}회(업로드 챕터 수) + 리포트 요약 LLM {llm_calls}회(신입당 4회)")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(exported, f, ensure_ascii=False)
        print(f"리포트 화면 점수 검증용 데이터: {out_path}")


# ── 실행 모드 (과금 발생) ─────────────────────────────────────────────

class Api:
    def __init__(self, base):
        import httpx

        self.client = httpx.Client(base_url=base, timeout=120)
        # 데모 계정은 rate limit을 user_id + 방문자 구분값으로 나눈다 (core/rate_limit.py)
        self.visitor = f"seed-{uuid.uuid4()}"

    @staticmethod
    def check(res, what):
        if res.status_code >= 400:
            raise RuntimeError(f"{what} 실패 ({res.status_code}): {res.text[:300]}")
        return res.json() if res.content else None

    def login(self, email):
        res = self.client.post("/user/login", json={"email": email, "password": DEMO_PASSWORD})
        return self.check(res, f"로그인 {email}")["access_token"]

    def call(self, method, path, token, what, **kwargs):
        headers = {"Authorization": f"Bearer {token}", "X-Visitor-Id": self.visitor}
        return self.check(self.client.request(method, path, headers=headers, **kwargs), what)


def wipe_company(db, key):
    """이 회사의 데모 데이터만 지운다 — 사수 계정 기준으로 이 사수가 올린 문서·배정한 신입까지."""
    from core.chroma_client import get_chroma_client
    from models.assignment import AssignmentORM
    from models.chat import ChatLogORM
    from models.checklist import ChecklistItemORM
    from models.document import DocumentChapterORM, DocumentMentorMapORM
    from models.report import AdaptationReportORM, ReportSectionORM
    from models.user import UserORM

    mentor_id = f"demo-mentor-{key}"
    emails = ([f"demo-mentor-{key}@handover.demo", f"demo-newcomer-{key}@handover.demo"]
              + [EXTRA_EMAIL.format(key=key, n=n) for n in (1, 2)])
    newcomer_ids = {u.user_id for u in db.query(UserORM).filter(UserORM.email.in_(emails), UserORM.role == "newcomer")}
    newcomer_ids |= {a.newcomer_id for a in db.query(AssignmentORM).filter(AssignmentORM.mentor_id == mentor_id)}
    newcomer_ids.add(f"demo-newcomer-{key}")

    ids = list(newcomer_ids)
    report_ids = [r.report_id for r in db.query(AdaptationReportORM).filter(AdaptationReportORM.newcomer_id.in_(ids))]
    if report_ids:
        db.query(ReportSectionORM).filter(ReportSectionORM.report_id.in_(report_ids)).delete(synchronize_session=False)
        db.query(AdaptationReportORM).filter(AdaptationReportORM.report_id.in_(report_ids)).delete(synchronize_session=False)
    db.query(ChatLogORM).filter(ChatLogORM.newcomer_id.in_(ids)).delete(synchronize_session=False)
    db.query(ChecklistItemORM).filter(ChecklistItemORM.newcomer_id.in_(ids)).delete(synchronize_session=False)
    db.query(AssignmentORM).filter(AssignmentORM.newcomer_id.in_(ids)).delete(synchronize_session=False)

    chroma = get_chroma_client()
    for doc in db.query(DocumentMentorMapORM).filter(DocumentMentorMapORM.mentor_id == mentor_id).all():
        db.query(DocumentChapterORM).filter(DocumentChapterORM.document_id == doc.document_id).delete(synchronize_session=False)
        try:
            chroma.delete_collection(doc.document_id)
        except Exception:  # noqa: BLE001 — 컬렉션이 없으면 지울 것도 없다
            pass
        db.delete(doc)

    db.query(UserORM).filter(UserORM.user_id.in_(ids + [mentor_id])).delete(synchronize_session=False)
    db.query(UserORM).filter(UserORM.email.in_(emails)).delete(synchronize_session=False)
    db.commit()


def execute(companies, api_base):
    from core.auth import hash_password
    from core.database import SessionLocal
    from models.assignment import AssignmentORM
    from models.chat import ChatLogORM
    from models.checklist import ChecklistItemORM
    from models.user import UserORM

    api = Api(api_base)
    db = SessionLocal()
    try:
        for spec in companies:
            key = spec["key"]
            mentor_id = f"demo-mentor-{key}"
            print(f"\n[{key}] {spec['company']}")
            _, plans = build_plan(spec)
            wipe_company(db, key)

            # 1) 고정 ID 계정 — 가입 API로는 ID를 지정할 수 없다
            db.add(UserORM(user_id=mentor_id, name=spec["mentor"], role="mentor",
                           email=f"demo-mentor-{key}@handover.demo", password_hash=hash_password(DEMO_PASSWORD)))
            db.add(UserORM(user_id=plans[0]["fixed_id"], name=plans[0]["name"], role="newcomer",
                           email=plans[0]["email"], password_hash=hash_password(DEMO_PASSWORD)))
            db.commit()
            plans[0]["user_id"] = plans[0]["fixed_id"]

            # 2) 추가 신입 — 일반 가입과 똑같이
            for plan in plans[1:]:
                res = api.client.post("/user/register", json={
                    "name": plan["name"], "email": plan["email"], "password": DEMO_PASSWORD, "role": "newcomer"})
                plan["user_id"] = api.check(res, f"가입 {plan['email']}")["user_id"]

            mentor_token = api.login(f"demo-mentor-{key}@handover.demo")

            # 3) 문서 업로드 — 과금(임베딩)
            with open(os.path.join(DEMO_FILES, f"{key}-handover.md"), "rb") as f:
                doc = api.call("POST", "/document/upload", mentor_token, "문서 업로드",
                               data={"mentor_id": mentor_id, "label": spec["label"]},
                               files=[("files", (f"{spec['label']}.md", f.read(), "text/markdown"))])
            chapter_id = {c["title"]: c["chapter_id"] for c in doc["chapters"]}
            print(f"  문서 업로드 — 업무 {len(doc['chapters'])}개")

            for plan in plans:
                nid = plan["user_id"]
                # 4) 배정 → 배정일을 과거로
                api.call("POST", "/assignment", mentor_token, "배정",
                         json={"mentor_id": mentor_id, "newcomer_id": nid, "document_id": doc["document_id"]})
                db.query(AssignmentORM).filter(AssignmentORM.newcomer_id == nid).update(
                    {"assigned_at": plan["assigned_at"]})

                # 5) 체크리스트 → 완료 시각을 과거로 (완료 API는 "지금"만 찍는다)
                created = api.call("POST", "/checklist", mentor_token, "체크리스트", json={"items": [
                    {"newcomer_id": nid, "chapter_id": chapter_id[c["chapter_title"]], "title": c["title"],
                     "order": i + 1, "source": c["source"]} for i, c in enumerate(plan["checklist"])]})
                for item, c in zip(created, plan["checklist"]):
                    if c["completed_at"]:
                        db.query(ChecklistItemORM).filter(ChecklistItemORM.item_id == item["item_id"]).update(
                            {"status": "done", "completed_at": c["completed_at"]})

                # 6) 챗로그 — 과거 시각으로
                for log in plan["logs"]:
                    db.add(ChatLogORM(
                        log_id=str(uuid.uuid4()), newcomer_id=nid, document_id=doc["document_id"],
                        question=log["question"], answer=log["answer"], answered=log["answered"],
                        matched_chapter_id=chapter_id.get(log["chapter_title"]),
                        question_type=log["question_type"], created_at=log["created_at"]))
                db.commit()

                # 7) 리포트 — 과금(LLM 4회). 서버가 위 데이터로 신호를 계산한다.
                time.sleep(4)  # 사용자·IP별 분당 제한(core/rate_limit.py)에 걸리지 않게
                report = api.call("POST", "/report/generate", mentor_token, f"리포트 {plan['name']}", json={
                    "newcomer_id": nid, "period_start": iso(plan["period_start"]), "period_end": iso(plan["period_end"])})
                print(f"  {plan['name']:<4} {plan['archetype']:<8} 체크리스트 5 · 질문 {len(plan['logs'])} · "
                      f"리포트 {report['report_id'][:8]}")
    finally:
        db.close()
    print(f"\n완료. 로그인: demo-mentor-{{a..d}} / demo-newcomer-{{a..d}} @handover.demo, 비밀번호 {DEMO_PASSWORD}")


def main():
    parser = argparse.ArgumentParser(description="데모 회사 4곳 시딩")
    parser.add_argument("--execute", action="store_true", help="실제로 넣는다 (OpenAI 과금 발생)")
    parser.add_argument("--only", choices=[c["key"] for c in COMPANIES], help="회사 한 곳만")
    parser.add_argument("--api", default=os.getenv("SEED_API_BASE", "http://localhost:8000"))
    parser.add_argument("--out", help="점검 모드: 리포트 화면 점수 검증용 JSON을 이 경로에 저장")
    args = parser.parse_args()

    companies = [c for c in COMPANIES if not args.only or c["key"] == args.only]
    if args.execute:
        execute(companies, args.api)
    else:
        dry_run(companies, args.out)


if __name__ == "__main__":
    main()
