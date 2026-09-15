# -*- coding: utf-8 -*-
"""routers/chat.py의 _node_search 테스트 — mock으로 OpenAI 임베딩 + ChromaDB를
둘 다 떼어냄 (guidelines 5-10).

지금까지 mock한 것들과 다른 점: chat_complete는 "함수"라서 lambda 하나로 바꿔치기가
됐는데, get_collection()은 "query()라는 메서드를 가진 객체"를 돌려주는 함수라서,
그 객체 자체를 흉내 낼 가짜 클래스가 하나 더 필요하다.

_node_search가 실제로 하는 일: ChromaDB가 돌려주는 원본 응답 형태
({"documents": [[...]], "metadatas": [[...]], "distances": [[...]]}, 바깥쪽 리스트가
"질문이 여러 개일 수도 있어서" 한 겹 더 감싸진 형태)를, 우리 코드가 쓰기 편한
[{"text":..., "chapter_id":..., "distance":...}] 형태로 정리하는 것. 이 "정리하는
로직"이 검증 대상이지, ChromaDB의 실제 검색 품질 자체는 (당연히) 대상이 아니다.
"""

from routers.chat import _node_search


class FakeCollection:
    """진짜 ChromaDB 컬렉션 대신 쓰는 가짜 — query()를 부르면 미리 정해둔 응답을 돌려준다."""

    def __init__(self, query_response: dict):
        self._query_response = query_response

    def query(self, **kwargs):
        return self._query_response


def test_builds_hits_list_from_chroma_response(monkeypatch):
    monkeypatch.setattr("routers.chat.embed_text", lambda question: [0.1, 0.2, 0.3])

    fake_response = {
        "documents": [["[챕터: 정산] 첫 번째 청크", "[챕터: 근태] 두 번째 청크"]],
        "metadatas": [[{"chapter_id": "ch-1"}, {"chapter_id": "ch-2"}]],
        "distances": [[0.4, 1.1]],
    }
    monkeypatch.setattr("routers.chat.get_collection", lambda document_id: FakeCollection(fake_response))

    state = {"document_id": "doc-1", "question": "정산은 언제 하나요?"}
    result = _node_search(state)

    assert result["search_results"] == [
        {"text": "[챕터: 정산] 첫 번째 청크", "chapter_id": "ch-1", "distance": 0.4},
        {"text": "[챕터: 근태] 두 번째 청크", "chapter_id": "ch-2", "distance": 1.1},
    ]


def test_empty_chroma_response_yields_empty_hits(monkeypatch):
    # 이 문서에 아직 임베딩된 청크가 하나도 없는 경우(막 업로드 직후 등) — 에러 없이
    # 빈 검색 결과로 처리돼야 그 다음 단계(_node_generate)가 정상적으로 "모른다"고 답한다.
    monkeypatch.setattr("routers.chat.embed_text", lambda question: [0.1])

    fake_response = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
    monkeypatch.setattr("routers.chat.get_collection", lambda document_id: FakeCollection(fake_response))

    state = {"document_id": "doc-1", "question": "아무 질문"}
    result = _node_search(state)

    assert result["search_results"] == []


def test_missing_metadata_becomes_none_chapter_id(monkeypatch):
    # ChromaDB가 이론상 metadata 없이 청크를 돌려줄 수도 있다 — 그런 경우
    # chapter_id를 억지로 만들어내지 않고 None으로 안전하게 처리되는지 확인.
    monkeypatch.setattr("routers.chat.embed_text", lambda question: [0.1])

    fake_response = {
        "documents": [["메타데이터 없는 청크"]],
        "metadatas": [[None]],
        "distances": [[0.9]],
    }
    monkeypatch.setattr("routers.chat.get_collection", lambda document_id: FakeCollection(fake_response))

    state = {"document_id": "doc-1", "question": "아무 질문"}
    result = _node_search(state)

    assert result["search_results"] == [{"text": "메타데이터 없는 청크", "chapter_id": None, "distance": 0.9}]
