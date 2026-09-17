# -*- coding: utf-8 -*-
"""routers/chat.py의 _node_generate 테스트 — mock으로 OpenAI 호출을 떼어냄 (guidelines 5-10).

지금까지의 테스트와 다른 점: _node_generate는 내부에서 실제 OpenAI를 부르는
chat_complete()를 쓰기 때문에 순수 함수가 아니다. 그래서 chat_complete을
"가짜"로 바꿔치기(mock)해서, "LLM이 이런 걸 돌려줬을 때 answered/answer/
matched_chapter_id를 올바르게 채우는가"라는 판단 로직만 떼어내서 검증한다.

중요한 mock 규칙 — "정의된 곳"이 아니라 "쓰이는 곳"을 패치한다:
  core/llm.py에 정의된 chat_complete을 patch("core.llm.chat_complete", ...)로
  바꾸면 안 통한다. routers/chat.py가 `from core.llm import chat_complete`로
  이미 자기 모듈 이름공간에 이름을 복사해와서 쓰고 있으므로, 실제로 바꿔야
  하는 건 "routers.chat.chat_complete"다.

_node_generate는 답변 생성 + 질문 유형 분류(_classify_question_type)까지
안에서 두 번 chat_complete를 부른다. 아래 가짜 함수는 어떤 프롬프트로
불렸든 항상 같은 값을 돌려주는 제일 단순한 형태라 — 두 번째 호출(분류)의
결과가 fact/procedure/judgment/advanced 중 하나가 아니게 되지만, 코드 쪽에
이미 "모르면 fact로 폴백" 처리가 있어서 에러 없이 넘어간다.
"""

from routers.chat import NO_ANSWER_MESSAGE, NOT_FOUND_SENTINEL, _node_generate


def test_marks_unanswered_when_llm_says_not_found(monkeypatch):
    monkeypatch.setattr("routers.chat.chat_complete", lambda **kwargs: NOT_FOUND_SENTINEL)

    state = {
        "question": "회사 주차장은 어디예요?",
        "search_results": [{"text": "발췌 내용", "chapter_id": "ch-1", "distance": 0.9}],
    }

    result = _node_generate(state)

    assert result["answered"] is False
    assert result["answer"] == NO_ANSWER_MESSAGE
    assert result["matched_chapter_id"] is None


def test_marks_answered_when_llm_gives_real_answer(monkeypatch):
    monkeypatch.setattr("routers.chat.chat_complete", lambda **kwargs: "정산은 매주 월요일에 진행합니다.")

    state = {
        "question": "정산은 언제 하나요?",
        "search_results": [{"text": "발췌 내용", "chapter_id": "ch-1", "distance": 0.3}],
    }

    result = _node_generate(state)

    assert result["answered"] is True
    assert result["answer"] == "정산은 매주 월요일에 진행합니다."
    assert result["matched_chapter_id"] == "ch-1"


def test_no_matched_chapter_when_there_were_no_search_results(monkeypatch):
    # 검색 결과가 아예 없으면(예: ChromaDB에 이 문서 데이터가 없음) 답변이 성공해도
    # 출처로 삼을 chapter_id 자체가 없어야 한다.
    monkeypatch.setattr("routers.chat.chat_complete", lambda **kwargs: "일반적인 답변입니다.")

    state = {"question": "아무 질문", "search_results": []}
    result = _node_generate(state)

    assert result["answered"] is True
    assert result["matched_chapter_id"] is None
