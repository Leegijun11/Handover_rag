# -*- coding: utf-8 -*-
"""routers/checklist_draft.py의 _node_generate_tasks 테스트 — mock으로 OpenAI 호출을
떼어냄 (guidelines 5-10). 챕터마다 LLM에게 "JSON 배열로 태스크를 뽑아라"고 시키는데,
LLM이 JSON 규칙을 안 지킬 수도 있으므로 그 방어 로직까지 검증한다.
"""

from routers.checklist_draft import _node_generate_tasks


def test_generates_items_per_chapter_with_correct_chapter_id(monkeypatch):
    # 챕터마다 프롬프트(user_prompt)에 챕터 제목이 들어가므로, 그걸 보고 챕터별로
    # 다른 응답을 돌려주는 가짜 함수를 만든다 — 실제로 여러 챕터를 순회하는지까지 검증.
    def fake_chat_complete(**kwargs):
        if "[챕터: 상품 등록]" in kwargs["user_prompt"]:
            return '["상품 등록 절차 따라해보기"]'
        if "[챕터: 정산]" in kwargs["user_prompt"]:
            return '["정산 주기 확인하기", "정산 담당자에게 문의해보기"]'
        return "[]"

    monkeypatch.setattr("routers.checklist_draft.chat_complete", fake_chat_complete)

    state = {
        "document_id": "doc-1",
        "chapters": [
            {"chapter_id": "ch-1", "title": "상품 등록", "content": "상품 등록 절차 설명..."},
            {"chapter_id": "ch-2", "title": "정산", "content": "정산 절차 설명..."},
        ],
        "items": [],
    }

    result = _node_generate_tasks(state)

    assert result["items"] == [
        {"title": "상품 등록 절차 따라해보기", "chapter_id": "ch-1"},
        {"title": "정산 주기 확인하기", "chapter_id": "ch-2"},
        {"title": "정산 담당자에게 문의해보기", "chapter_id": "ch-2"},
    ]


def test_grouping_only_chapters_are_skipped_without_calling_llm(monkeypatch):
    calls = []

    def fake_chat_complete(**kwargs):
        calls.append(kwargs["user_prompt"])
        return '["태스크"]'

    monkeypatch.setattr("routers.checklist_draft.chat_complete", fake_chat_complete)

    state = {
        "document_id": "doc-1",
        "chapters": [
            {"chapter_id": "ch-1", "title": "그룹핑용 상위", "content": None},  # content 없음
            {"chapter_id": "ch-2", "title": "실제 내용", "content": "본문"},
        ],
        "items": [],
    }

    result = _node_generate_tasks(state)

    assert len(calls) == 1  # content=None인 챕터는 LLM 호출 자체가 아예 안 일어나야 함
    assert result["items"] == [{"title": "태스크", "chapter_id": "ch-2"}]


def test_malformed_json_response_yields_no_items_for_that_chapter(monkeypatch):
    # LLM이 "JSON 배열로만 답하라"는 지시를 어기고 자연어로 답해버린 경우 —
    # 에러로 죽지 않고 그 챕터만 태스크 0개로 넘어가야 한다.
    monkeypatch.setattr("routers.checklist_draft.chat_complete", lambda **kwargs: "이건 JSON이 아닙니다")

    state = {
        "document_id": "doc-1",
        "chapters": [{"chapter_id": "ch-1", "title": "T", "content": "본문"}],
        "items": [],
    }

    result = _node_generate_tasks(state)

    assert result["items"] == []


def test_non_string_entries_in_json_array_are_ignored(monkeypatch):
    monkeypatch.setattr("routers.checklist_draft.chat_complete", lambda **kwargs: '["진짜 태스크", 123, null]')

    state = {
        "document_id": "doc-1",
        "chapters": [{"chapter_id": "ch-1", "title": "T", "content": "본문"}],
        "items": [],
    }

    result = _node_generate_tasks(state)

    assert result["items"] == [{"title": "진짜 태스크", "chapter_id": "ch-1"}]
