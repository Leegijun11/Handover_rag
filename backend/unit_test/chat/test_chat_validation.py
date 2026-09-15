# -*- coding: utf-8 -*-
"""routers/chat.py의 AskRequest 검증 테스트 (guidelines 5-10, 5-9번 항목 2).

Pydantic 모델 자체를 직접 만들어서 검증하는 테스트라 FastAPI 서버를 띄우거나
DB/OpenAI를 건드리지 않는다. 최근에 추가한 "질문 500자 제한(서버 측)"이 실제로
동작하는지 — 프론트 제한을 우회해서 API를 직접 두드려도 막히는지 — 를 고정해둔다.
"""

import pytest
from pydantic import ValidationError

from routers.chat import AskRequest


def test_normal_question_is_accepted():
    req = AskRequest(newcomer_id="newcomer-1", question="정산 마감일이 언제예요?")

    assert req.question == "정산 마감일이 언제예요?"


def test_question_at_exactly_500_chars_is_accepted():
    req = AskRequest(newcomer_id="newcomer-1", question="가" * 500)

    assert len(req.question) == 500


def test_question_over_500_chars_is_rejected():
    with pytest.raises(ValidationError):
        AskRequest(newcomer_id="newcomer-1", question="가" * 501)


def test_empty_question_is_rejected():
    with pytest.raises(ValidationError):
        AskRequest(newcomer_id="newcomer-1", question="")


def test_missing_newcomer_id_is_rejected():
    with pytest.raises(ValidationError):
        AskRequest(question="질문만 있고 신입 id가 없음")
