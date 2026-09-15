# -*- coding: utf-8 -*-
"""routers/report.py의 _node_compute_signals 테스트 — mock으로 OpenAI 호출을 떼어냄
(guidelines 5-10). test_report_signals.py는 신호 4개의 "계산" 자체(_compute_*, 순수
함수)를 다뤘고, 이 파일은 그 위에서 "계산 결과 4개를 LLM 요약과 함께 섹션 4개로
조립하는" 단계(_node_compute_signals, _summarize를 4번 호출함)를 다룬다.
"""

from datetime import datetime, timedelta, timezone

from routers.report import _node_compute_signals

NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)


def test_assembles_exactly_four_sections_in_fixed_order(monkeypatch):
    monkeypatch.setattr("routers.report.chat_complete", lambda **kwargs: "요약 텍스트")

    state = {
        "newcomer_id": "n-1",
        "period_start": NOW,
        "period_end": NOW + timedelta(days=10),
        "chat_logs": [],
        "checklist_items": [],
        "sections": [],
    }

    result = _node_compute_signals(state)

    signal_types = [s["signal_type"] for s in result["sections"]]
    assert signal_types == ["growth_curve", "chapter_heatmap", "gap_task", "silence_risk"]


def test_each_section_gets_the_mocked_summary(monkeypatch):
    monkeypatch.setattr("routers.report.chat_complete", lambda **kwargs: "요약 텍스트")

    state = {
        "newcomer_id": "n-1",
        "period_start": NOW,
        "period_end": NOW + timedelta(days=10),
        "chat_logs": [],
        "checklist_items": [],
        "sections": [],
    }

    result = _node_compute_signals(state)

    assert all(section["summary"] == "요약 텍스트" for section in result["sections"])


def test_section_data_matches_already_tested_compute_functions(monkeypatch):
    # _compute_growth_curve 등은 test_report_signals.py에서 이미 따로 검증했으므로,
    # 여기서는 "그 계산 결과가 조립 단계에서 올바른 section에 올바르게 담기는지"만 본다.
    monkeypatch.setattr("routers.report.chat_complete", lambda **kwargs: "요약")

    chat_logs = [
        {"question_type": "fact", "matched_chapter_id": "ch-1", "created_at": NOW},
        {"question_type": "procedure", "matched_chapter_id": "ch-1", "created_at": NOW},
    ]
    state = {
        "newcomer_id": "n-1",
        "period_start": NOW,
        "period_end": NOW + timedelta(days=10),
        "chat_logs": chat_logs,
        "checklist_items": [],
        "sections": [],
    }

    result = _node_compute_signals(state)

    growth_section = next(s for s in result["sections"] if s["signal_type"] == "growth_curve")
    assert growth_section["data"]["total"] == 2

    heatmap_section = next(s for s in result["sections"] if s["signal_type"] == "chapter_heatmap")
    assert heatmap_section["data"]["counts"] == {"ch-1": 2}
