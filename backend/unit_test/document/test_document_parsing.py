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


def test_two_level_headers_keep_depth_and_empty_group_chapters():
    """대분류 아래 소분류가 오면 계층 정보(level)가 남아야 하고, 본문 없는 대분류도 살아야 한다.

    이게 깨지면 리포트의 업무 범위 점수가 대분류가 아니라 소분류 개수로 계산되고(점수가
    구조적으로 낮아짐), 체크리스트 관리 화면의 소분류 선택이 영원히 비어 있게 된다 — 9/17에
    실제로 그 상태였다.
    """
    text = "# 정산\n## 정산 마감 일정\n마감은 매월 15일이다.\n\n## 정산 예외 처리\n예외는 따로 적는다.\n\n# 반품\n## 반품 처리\n회수부터 확인한다."
    chapters = _parse_chapters_from_text(text)

    titles = [(c["title"], c["level"]) for c in chapters]
    assert titles == [
        ("정산", 1),
        ("정산 마감 일정", 2),
        ("정산 예외 처리", 2),
        ("반품", 1),
        ("반품 처리", 2),
    ]
    # 대분류 "정산"은 바로 아래에 소분류가 와서 본문이 비지만, 목록에서 사라지면 안 된다
    assert chapters[0]["content"] == ""


def test_numbered_sub_items_are_second_level():
    text = "1. 배차\n당일 물량 기준.\n\n1-1. 당일 배차 절차\n오전 9시에 받는다.\n\n2. 사고 대응\n먼저 보고한다."
    chapters = _parse_chapters_from_text(text)

    assert [(c["title"], c["level"]) for c in chapters] == [
        ("배차", 1),
        ("당일 배차 절차", 2),
        ("사고 대응", 1),
    ]
