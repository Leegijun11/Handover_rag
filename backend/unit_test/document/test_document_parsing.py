# -*- coding: utf-8 -*-
"""routers/document.py의 _parse_chapters_from_text 테스트 (guidelines 5-10).

DB/OpenAI 호출이 전혀 없는 순수 함수라 서버를 띄우거나 .env를 채우지 않고도
그대로 돌아간다 — 이런 함수부터 테스트를 붙이는 게 제일 쉽고 안전하다.

이 세션 동안 실제로 손으로 반복했던 확인("이 텍스트를 올리면 챕터가 몇 개로
나뉘나")을 코드로 고정해둔 것 — 나중에 파싱 로직을 고치다가 실수로 망가뜨리면
이 테스트가 바로 알려준다.
"""

import pytest
from fastapi import HTTPException

from routers.document import _parse_chapters_from_text


def test_markdown_header_splits_into_chapters():
    text = "# 담당 업무 개요\n첫 번째 챕터 내용입니다.\n\n# 매입 처리\n두 번째 챕터 내용입니다."
    chapters = _parse_chapters_from_text(text)

    assert len(chapters) == 2
    assert chapters[0]["title"] == "담당 업무 개요"
    assert chapters[0]["fallback"] is False
    assert chapters[1]["title"] == "매입 처리"


def test_numbered_header_splits_into_chapters():
    text = "1. 채용 프로세스\n채용 관련 내용.\n\n2. 근로계약\n계약 관련 내용."
    chapters = _parse_chapters_from_text(text)

    assert len(chapters) == 2
    assert chapters[0]["title"] == "채용 프로세스"
    assert chapters[1]["title"] == "근로계약"


def test_single_header_falls_back_to_one_chapter():
    # 헤더가 1개뿐이면(구조로 볼 근거가 부족) 자동 분리를 포기하고 전체를 한 챕터로 묶는다.
    text = "# 유일한 제목\n본문 전체가 여기 다 들어있습니다."
    chapters = _parse_chapters_from_text(text)

    assert len(chapters) == 1
    assert chapters[0]["fallback"] is True


def test_no_headers_falls_back_to_single_chapter_with_given_title():
    text = "그냥 평범한 문단입니다. 목차 표시가 전혀 없습니다."
    chapters = _parse_chapters_from_text(text, fallback_title="상품팀")

    assert len(chapters) == 1
    assert chapters[0]["title"] == "상품팀"
    assert chapters[0]["fallback"] is True


def test_empty_text_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        _parse_chapters_from_text("   ")  # 공백만 있는 경우도 빈 것으로 취급

    assert exc_info.value.status_code == 400
