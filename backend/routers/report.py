"""적응도 리포트 (담당: 조장) — guidelines 3-6, 3-9, 4-1, 5-9.

핵심 흐름:
  1. newcomer_id 기준 ChatLog + ChecklistItem(완료 로그) 조회
  2. 4개 신호 계산: growth_curve / chapter_heatmap / gap_task / silence_risk
  3. 신호별 LLM 요약(summary) 생성 — 질문 원문 그대로 노출 금지, 패턴 단위로만 서술
  4. AdaptationReport로 저장 (generated_at = 실제 생성 시각) 후 반환
"""

import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException, Request
from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import CurrentUser, get_current_user, require_role
from core.database import get_db
from core.llm import REPORT_MODEL, chat_complete
from core.rate_limit import IP_RATE_LIMIT, USER_RATE_LIMIT, ip_limiter, user_limiter
from models.assignment import get_assignment_by_newcomer
from models.chat import ChatLogORM
from models.checklist import ChecklistItemORM
from models.report import AdaptationReportORM, ReportSectionORM
from schemas.report import AdaptationReport, ReportSection

router = APIRouter(tags=["report"])

# 같은 newcomer_id로 마지막 생성 후 이 시간 안에 재요청하면 429 (guidelines 5-9 항목 4)
MIN_REGENERATE_INTERVAL = timedelta(minutes=5)
# Assignment.assigned_at 연동 전까지 최초 리포트 기간의 임시 폴백 (연동되면 안 쓰임)
FALLBACK_PERIOD_DAYS = 30


class GenerateReportRequest(BaseModel):
    newcomer_id: str
    period_start: datetime | None = None
    period_end: datetime | None = None


def _get_assignment_assigned_at(db: Session, newcomer_id: str) -> datetime | None:
    """최초 리포트의 period_start 기본값("Assignment 생성일 ~ 지금", guidelines 3-6)에 씀."""
    row = get_assignment_by_newcomer(db, newcomer_id)
    return row.assigned_at if row else None


def _require_mentor_owns_newcomer(db: Session, current_user: CurrentUser, newcomer_id: str) -> None:
    """이 사수가 실제로 이 신입을 담당하는지 검증 (guidelines 3-9 조회 권한 원칙).

    이전엔 require_role(mentor)만 확인해서, mentor_id/newcomer_id 매칭 없이 role만
    맞으면 어떤 사수든 newcomer_id만 알면 남의 신입 리포트를 조회·생성할 수 있었다
    (TODO로 표시돼 있었으나 미해결 상태였음 — 실제로 재현 가능한 취약점이었음).
    """
    assignment = get_assignment_by_newcomer(db, newcomer_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="배정된 적 없는 신입입니다")
    if assignment.mentor_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="본인이 담당하는 신입이 아닙니다")


def _get_checklist_items(db: Session, newcomer_id: str) -> list[dict]:
    """gap_task 신호(완료 후에도 관련 질문이 이어진 항목) 계산에 씀."""
    rows = db.query(ChecklistItemORM).filter_by(newcomer_id=newcomer_id).all()
    return [
        {"title": r.title, "chapter_id": r.chapter_id, "completed_at": r.completed_at}
        for r in rows
    ]


class ReportState(TypedDict):
    newcomer_id: str
    period_start: datetime
    period_end: datetime
    chat_logs: list[dict]
    checklist_items: list[dict]
    sections: list[dict]


def _make_load_data_node(db: Session):
    def _node(state: ReportState) -> ReportState:
        logs = (
            db.query(ChatLogORM)
            .filter(
                ChatLogORM.newcomer_id == state["newcomer_id"],
                ChatLogORM.created_at >= state["period_start"],
                ChatLogORM.created_at <= state["period_end"],
            )
            .order_by(ChatLogORM.created_at)
            .all()
        )
        state["chat_logs"] = [
            {
                "question_type": row.question_type,
                "matched_chapter_id": row.matched_chapter_id,
                "answered": row.answered,
                "created_at": row.created_at,
            }
            for row in logs
        ]
        state["checklist_items"] = _get_checklist_items(db, state["newcomer_id"])
        return state

    return _node


def _compute_growth_curve(chat_logs: list[dict]) -> dict:
    counts = Counter(log["question_type"] for log in chat_logs)
    return {"counts": dict(counts), "total": len(chat_logs)}


def _compute_chapter_heatmap(chat_logs: list[dict]) -> dict:
    counts = Counter(log["matched_chapter_id"] for log in chat_logs if log["matched_chapter_id"])
    return {"counts": dict(counts)}


def _compute_gap_task(checklist_items: list[dict], chat_logs: list[dict]) -> dict:
    gaps = []
    for item in checklist_items:
        completed_at = item.get("completed_at")
        if not completed_at:
            continue
        related_after = [
            log
            for log in chat_logs
            if log["matched_chapter_id"] == item.get("chapter_id") and log["created_at"] > completed_at
        ]
        if related_after:
            gaps.append({"title": item.get("title"), "question_count_after_complete": len(related_after)})
    return {"gap_items": gaps}


def _compute_silence_risk(chat_logs: list[dict], period_start: datetime, period_end: datetime) -> dict:
    if not chat_logs:
        return {"dropped_sharply": False, "reason": "no_questions_in_period"}
    # 단순 휴리스틱(재량): 기간을 절반으로 나눠 후반부 질문 수가 전반부 대비 급감했는지.
    midpoint = period_start + (period_end - period_start) / 2
    first_half = sum(1 for log in chat_logs if log["created_at"] < midpoint)
    second_half = sum(1 for log in chat_logs if log["created_at"] >= midpoint)
    dropped = first_half > 0 and second_half <= first_half * 0.3
    return {
        "first_half_questions": first_half,
        "second_half_questions": second_half,
        "dropped_sharply": dropped,
    }


# 신호마다 "이 숫자가 무엇인지"를 프롬프트에 같이 넘긴다. 신호 이름과 값만 주면 모델이 값을
# 제멋대로 해석한다 — 실제로 업무별 질문 횟수를 "12명이 긍정적인 반응을 보였다"로, 완료 후 다시
# 물은 항목이 없는 것(좋은 신호)을 "판단할 데이터가 부족하다"로 쓴 사례가 나왔다 (팀원 B 확인, 9/16).
_SIGNAL_GUIDE = {
    "growth_curve": (
        "질문을 유형별로 센 결과다. counts의 fact=사실 확인, procedure=절차, judgment=판단, "
        "advanced=심화 질문 건수이고 total은 전체 질문 수다. 점수나 평가 항목이 아니라 질문 건수다. "
        "사실 확인에서 절차·판단·심화로 옮겨갈수록 업무를 깊이 파고드는 것으로 본다."
    ),
    "chapter_heatmap": (
        "인수인계서의 업무(챕터)별 질문 횟수다. 키는 업무 식별자이고 값은 그 업무에 대한 질문 건수다. "
        "사람 수나 점수, 응답률이 아니다. 질문이 한 번이라도 있었던 업무만 들어 있어서 전체 업무 수는 "
        "알 수 없으니, 묻지 않은 업무가 있는지 없는지는 말하지 마라. 업무 이름도 모르니 "
        "'특정 업무에 질문이 몰렸다'처럼 개수 위주로만 서술해라."
    ),
    "gap_task": (
        "체크리스트에서 완료로 체크한 뒤에도 같은 업무를 다시 물은 항목이다. title은 항목 이름, "
        "question_count_after_complete는 완료 이후 질문 건수다. 목록이 비어 있으면 데이터가 없는 "
        "것이 아니라 '완료한 업무를 다시 묻지 않았다'는 좋은 신호이니 그렇게 서술해라."
    ),
    "silence_risk": (
        "리포트 기간을 반으로 나눠 앞쪽·뒤쪽 질문 수를 센 결과다. dropped_sharply가 true면 뒤쪽에서 "
        "질문이 크게 줄어 신입이 혼자 막혀 있을 수 있다는 뜻이고, false면 질문이 이어지고 있다는 뜻이다. "
        "질문이 줄어든 것 자체가 곧 문제라고 단정하지는 마라."
    ),
}


def _summarize(signal_type: str, data: dict) -> str:
    return chat_complete(
        system_prompt=(
            "너는 신입사원의 적응 상태를 사수에게 설명하는 사람이다. 아래는 집계 데이터이고 질문 "
            f"원문은 없다.\n\n[이 데이터의 의미] {_SIGNAL_GUIDE.get(signal_type, '')}\n\n"
            "규칙:\n"
            "- 2~3문장, 사수가 바로 읽을 수 있는 평이한 한국어로 쓴다.\n"
            f"- '{signal_type}' 같은 내부 신호 이름이나 영어 필드명을 문장에 쓰지 않는다.\n"
            "- 데이터에 없는 사람 수·점수·비율을 지어내지 않는다.\n"
            "- 질문 건수는 '건'으로 센다. 사람 수나 점수로 바꿔 말하지 않는다.\n"
            "- 값이 비어 있을 때만 판단할 데이터가 부족하다고 말한다. 위 설명에서 '비어 있으면 좋은 "
            "신호'라고 한 경우는 그렇게 쓴다.\n"
            "- 평가하거나 단정하지 말고, 사수가 무엇을 살펴보면 좋을지로 마무리한다."
        ),
        user_prompt=str(data),
        model=REPORT_MODEL,
        max_tokens=300,
    )


def _node_compute_signals(state: ReportState) -> ReportState:
    growth = _compute_growth_curve(state["chat_logs"])
    heatmap = _compute_chapter_heatmap(state["chat_logs"])
    gap = _compute_gap_task(state["checklist_items"], state["chat_logs"])
    silence = _compute_silence_risk(state["chat_logs"], state["period_start"], state["period_end"])

    state["sections"] = [
        {"signal_type": "growth_curve", "data": growth, "summary": _summarize("growth_curve", growth)},
        {"signal_type": "chapter_heatmap", "data": heatmap, "summary": _summarize("chapter_heatmap", heatmap)},
        {"signal_type": "gap_task", "data": gap, "summary": _summarize("gap_task", gap)},
        {"signal_type": "silence_risk", "data": silence, "summary": _summarize("silence_risk", silence)},
    ]
    return state


def _build_graph(db: Session):
    graph = StateGraph(ReportState)
    graph.add_node("load_data", _make_load_data_node(db))
    graph.add_node("compute_signals", _node_compute_signals)
    graph.set_entry_point("load_data")
    graph.add_edge("load_data", "compute_signals")
    graph.add_edge("compute_signals", END)
    return graph.compile()


def _to_schema(report_row: AdaptationReportORM, sections: list[dict]) -> AdaptationReport:
    return AdaptationReport(
        report_id=report_row.report_id,
        newcomer_id=report_row.newcomer_id,
        period_start=report_row.period_start,
        period_end=report_row.period_end,
        generated_at=report_row.generated_at,
        sections=[ReportSection(**s) for s in sections],
    )


@router.post("/report/generate")
@user_limiter.limit(USER_RATE_LIMIT)
@ip_limiter.limit(IP_RATE_LIMIT)
def generate_report(
    request: Request,
    payload: GenerateReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")
    _require_mentor_owns_newcomer(db, current_user, payload.newcomer_id)

    # DB의 datetime은 전부 tz 정보 없는 UTC라, 여기서도 naive UTC로 맞춘다. tz-aware 값을 쓰면
    # 아래 재생성 간격 비교(now - generated_at)에서 TypeError가 나서, 같은 신입의 두 번째
    # 리포트 생성이 항상 500으로 떨어졌다 (팀원 B 확인·수정, 9/17).
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    last_report = (
        db.query(AdaptationReportORM)
        .filter_by(newcomer_id=payload.newcomer_id)
        .order_by(AdaptationReportORM.generated_at.desc())
        .first()
    )

    if last_report and now - last_report.generated_at < MIN_REGENERATE_INTERVAL:
        raise HTTPException(status_code=429, detail="너무 최근에 리포트를 생성했습니다. 잠시 후 다시 시도하세요")

    period_end = payload.period_end or now
    if payload.period_start:
        period_start = payload.period_start
    elif last_report:
        period_start = last_report.period_end
    else:
        assigned_at = _get_assignment_assigned_at(db, payload.newcomer_id)
        period_start = assigned_at or (period_end - timedelta(days=FALLBACK_PERIOD_DAYS))

    graph = _build_graph(db)
    result = graph.invoke(
        {
            "newcomer_id": payload.newcomer_id,
            "period_start": period_start,
            "period_end": period_end,
            "chat_logs": [],
            "checklist_items": [],
            "sections": [],
        }
    )

    report_id = str(uuid.uuid4())
    report_row = AdaptationReportORM(
        report_id=report_id,
        newcomer_id=payload.newcomer_id,
        period_start=period_start,
        period_end=period_end,
        generated_at=now,
    )
    db.add(report_row)
    for section in result["sections"]:
        db.add(
            ReportSectionORM(
                section_id=str(uuid.uuid4()),
                report_id=report_id,
                signal_type=section["signal_type"],
                summary=section["summary"],
                data=section["data"],
            )
        )
    db.commit()

    return _to_schema(report_row, result["sections"])


@router.get("/report/{newcomer_id}")
def get_latest_report(
    newcomer_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")
    _require_mentor_owns_newcomer(db, current_user, newcomer_id)
    row = (
        db.query(AdaptationReportORM)
        .filter_by(newcomer_id=newcomer_id)
        .order_by(AdaptationReportORM.generated_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="리포트가 없습니다")
    sections = [{"signal_type": s.signal_type, "summary": s.summary, "data": s.data} for s in row.sections]
    return _to_schema(row, sections)


@router.get("/report/{newcomer_id}/history")
def get_report_history(
    newcomer_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")
    _require_mentor_owns_newcomer(db, current_user, newcomer_id)
    rows = (
        db.query(AdaptationReportORM)
        .filter_by(newcomer_id=newcomer_id)
        .order_by(AdaptationReportORM.generated_at.desc())
        .all()
    )
    return [
        _to_schema(row, [{"signal_type": s.signal_type, "summary": s.summary, "data": s.data} for s in row.sections])
        for row in rows
    ]
