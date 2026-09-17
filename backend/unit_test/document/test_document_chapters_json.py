# -*- coding: utf-8 -*-
"""routers/document.py의 _parse_chapters_json 테스트 (guidelines 5-10).

"직접 입력"(사수가 챕터를 화면에서 하나씩 타이핑) 업로드 경로의 검증 로직.
_parse_chapters_from_text(파일 업로드용, 목차를 자동 인식)와 짝을 이루는 함수지만,
이쪽은 이미 구조가 확정된 입력이 맞는 형식으로 왔는지만 확인한다.
"""

import pytest
from fastapi import HTTPException

from routers.document import _parse_chapters_json


def test_valid_json_is_parsed_into_chapter_dicts():
    raw = '[{"title": "채용 프로세스", "content": "본문1"}, {"title": "근로계약", "content": "본문2"}]'

    chapters = _parse_chapters_json(raw)

    # 직접 입력 경로는 평면 구조라 level은 항상 1이다 (파일 업로드만 대분류·소분류를 나눈다)
    assert chapters == [
        {"title": "채용 프로세스", "content": "본문1", "level": 1, "fallback": False},
        {"title": "근로계약", "content": "본문2", "level": 1, "fallback": False},
    ]


def test_malformed_json_is_rejected():
    raw = "이건 JSON이 아니라 그냥 문자열입니다"

    with pytest.raises(HTTPException) as exc_info:
        _parse_chapters_json(raw)

    assert exc_info.value.status_code == 400


def test_missing_required_field_is_rejected():
    # content 없이 title만 있는 항목 -> ChapterInput 검증에서 걸려야 함
    raw = '[{"title": "채용 프로세스"}]'

    with pytest.raises(HTTPException) as exc_info:
        _parse_chapters_json(raw)

    assert exc_info.value.status_code == 400


def test_wrong_shape_is_rejected():
    # 객체 리스트가 아니라 문자열 리스트가 온 경우 (TypeError 경로)
    raw = '["채용 프로세스", "근로계약"]'

    with pytest.raises(HTTPException):
        _parse_chapters_json(raw)


def test_empty_list_is_accepted_as_empty_chapters():
    # 빈 리스트 자체는 형식상 잘못된 게 아니다 (업로드 엔드포인트가 그 뒤에서
    # "챕터가 하나도 없으면"을 따로 처리함 — 이 함수 책임은 형식 검증까지).
    chapters = _parse_chapters_json("[]")

    assert chapters == []
