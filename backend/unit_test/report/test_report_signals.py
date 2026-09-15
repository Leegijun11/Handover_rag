# -*- coding: utf-8 -*-
"""routers/report.py의 4개 신호 계산 함수 테스트 (guidelines 5-10).

_compute_* 함수들은 ChatLog/ChecklistItem을 이미 dict로 변환해서 받는 순수 함수라
(DB 조회는 _make_load_data_node가 미리 해둠) 여기서도 DB/OpenAI 없이 테스트 가능.

리포트는 신입의 적응도를 판단하는 핵심 기능이라, 신호 계산 로직이 조용히 틀려도
겉보기엔 리포트가 "그냥 생성"되기 때문에 사람이 눈으로 잘못을 알아채기 어렵다 —
이런 로직일수록 테스트로 기대값을 고정해두는 실익이 크다.
"""

from datetime import datetime, timedelta, timezone

from routers.report import (
    _compute_chapter_heatmap,
    _compute_gap_task,
    _compute_growth_curve,
    _compute_silence_risk,
)

NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


def log(question_type="fact", chapter_id="ch-1", created_at=NOW):
    return {"question_type": question_type, "matched_chapter_id": chapter_id, "created_at": created_at}


def test_growth_curve_counts_by_question_type():
    logs = [log(question_type="fact"), log(question_type="fact"), log(question_type="procedure")]

    result = _compute_growth_curve(logs)

    assert result["counts"] == {"fact": 2, "procedure": 1}
    assert result["total"] == 3


def test_growth_curve_empty_logs():
    result = _compute_growth_curve([])

    assert result["counts"] == {}
    assert result["total"] == 0


def test_chapter_heatmap_ignores_logs_without_matched_chapter():
    # 답변 실패(answered=false)해서 matched_chapter_id가 None인 로그는 히트맵에서 빠져야 한다
    # — 안 그러면 "못 찾은 질문"이 특정 업무에 몰린 것처럼 잘못 집계된다.
    logs = [log(chapter_id="ch-1"), log(chapter_id="ch-1"), log(chapter_id=None), log(chapter_id="ch-2")]

    result = _compute_chapter_heatmap(logs)

    assert result["counts"] == {"ch-1": 2, "ch-2": 1}


def test_gap_task_detects_question_after_completion():
    completed_at = NOW
    checklist_items = [{"title": "정산 절차 읽기", "chapter_id": "ch-1", "completed_at": completed_at}]
    chat_logs = [
        log(chapter_id="ch-1", created_at=completed_at + timedelta(hours=1)),  # 완료 이후 질문 -> gap
        log(chapter_id="ch-1", created_at=completed_at - timedelta(hours=1)),  # 완료 이전 질문 -> 무관
    ]

    result = _compute_gap_task(checklist_items, chat_logs)

    assert len(result["gap_items"]) == 1
    assert result["gap_items"][0]["title"] == "정산 절차 읽기"
    assert result["gap_items"][0]["question_count_after_complete"] == 1


def test_gap_task_ignores_uncompleted_items():
    # completed_at이 없으면(아직 체크 안 함)애초에 "완료 후 재질문" 신호가 성립하지 않는다.
    checklist_items = [{"title": "아직 안 함", "chapter_id": "ch-1", "completed_at": None}]
    chat_logs = [log(chapter_id="ch-1", created_at=NOW + timedelta(hours=1))]

    result = _compute_gap_task(checklist_items, chat_logs)

    assert result["gap_items"] == []


def test_silence_risk_no_questions_in_period():
    result = _compute_silence_risk([], NOW, NOW + timedelta(days=10))

    assert result["dropped_sharply"] is False
    assert result["reason"] == "no_questions_in_period"


def test_silence_risk_detects_sharp_drop():
    period_start = NOW
    period_end = NOW + timedelta(days=10)
    midpoint = period_start + (period_end - period_start) / 2
    # 전반부에 8건, 후반부에 1건 -> 70% 넘게 급감 -> 감지돼야 함
    chat_logs = [log(created_at=period_start + timedelta(hours=i)) for i in range(8)]
    chat_logs.append(log(created_at=midpoint + timedelta(hours=1)))

    result = _compute_silence_risk(chat_logs, period_start, period_end)

    assert result["first_half_questions"] == 8
    assert result["second_half_questions"] == 1
    assert result["dropped_sharply"] is True


def test_silence_risk_steady_activity_not_flagged():
    period_start = NOW
    period_end = NOW + timedelta(days=10)
    midpoint = period_start + (period_end - period_start) / 2
    # 전반부 4건, 후반부 4건 -> 급감 아님
    chat_logs = [log(created_at=period_start + timedelta(hours=i)) for i in range(4)]
    chat_logs += [log(created_at=midpoint + timedelta(hours=i + 1)) for i in range(4)]

    result = _compute_silence_risk(chat_logs, period_start, period_end)

    assert result["dropped_sharply"] is False
