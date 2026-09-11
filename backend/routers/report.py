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


def _summarize(signal_type: str, data: dict) -> str:
    return chat_complete(
        system_prompt=(
            f"아래는 신입사원 적응도 신호 '{signal_type}' 계산 결과(집계 데이터, 질문 원문 없음)다. "
            "이 패턴을 사수가 이해할 수 있도록 2~3문장 자연어로 요약해라. 숫자를 그대로 나열하지 "
            "말고 의미를 해석해서 서술해라. 데이터가 비어 있으면 '아직 판단할 데이터가 부족하다'는 "
            "취지로 답해라."
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
    # TODO(연동 필요 — 팀원 B): 이 mentor가 실제로 이 newcomer_id를 담당하는지 Assignment로
    # 검증해야 함(3-9 문서 조회 권한과 같은 취지). 지금은 role=mentor면 통과.

    now = datetime.now(timezone.utc)

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
