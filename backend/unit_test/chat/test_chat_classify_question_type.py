# -*- coding: utf-8 -*-
"""routers/chat.py의 _classify_question_type 테스트 — mock으로 OpenAI 호출을 떼어냄
(guidelines 5-10). LLM이 뭐라고 답하든 4가지 값 중 하나로만 정규화되는지, 그리고
엉뚱한 값을 주면 "fact"로 안전하게 폴백하는지를 확인한다.
"""

from routers.chat import _classify_question_type


def test_valid_classification_is_returned_as_is(monkeypatch):
    monkeypatch.setattr("routers.chat.chat_complete", lambda **kwargs: "procedure")

    result = _classify_question_type("정산은 어떻게 하나요?")

    assert result == "procedure"


def test_whitespace_and_case_are_normalized(monkeypatch):
    # 시스템 프롬프트가 "그 단어 하나만 출력하라"고 시켜도 LLM이 줄바꿈/대문자를 섞어
    # 줄 수 있다 — .strip().lower()로 정규화하는지 확인.
    monkeypatch.setattr("routers.chat.chat_complete", lambda **kwargs: "  Advanced\n")

    result = _classify_question_type("이 정책의 예외 상황은 어떻게 판단하나요?")

    assert result == "advanced"


def test_unrecognized_response_falls_back_to_fact(monkeypatch):
    # LLM이 지시를 안 지키고 엉뚱한 문장을 돌려주는 경우 — 4개 값 중 하나가 아니면
    # 무조건 "fact"로 폴백해야 리포트의 growth_curve 집계가 에러 없이 돌아간다.
    monkeypatch.setattr("routers.chat.chat_complete", lambda **kwargs: "잘 모르겠습니다")

    result = _classify_question_type("아무 질문")

    assert result == "fact"
