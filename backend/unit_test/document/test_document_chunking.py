# -*- coding: utf-8 -*-
"""routers/document.py의 _chunk_text 테스트 (guidelines 5-10).

_parse_chapters_from_text(챕터 나누기)와는 다른 단계 — 챕터 하나의 본문을 다시
ChromaDB 저장/임베딩용 작은 조각(청크)으로 잘게 쪼개는 함수. 임베딩 자체(_embed_texts,
OpenAI 호출)는 여기서 다루지 않는다 — "쪼개는 로직"까지만 순수 함수라 테스트 가능.
"""

from routers.document import _chunk_text


def test_short_text_becomes_a_single_chunk():
    chunks = _chunk_text("짧은 문장입니다.", "테스트 챕터")

    assert len(chunks) == 1
    assert chunks[0] == "[업무: 테스트 챕터] 짧은 문장입니다."


def test_long_text_splits_into_multiple_chunks():
    text = "첫 번째 문장입니다. 두 번째 문장입니다. 세 번째 문장입니다. 네 번째 문장입니다."
    # chunk_size를 작게 줘서(기본 500이면 이 텍스트가 안 잘림) 강제로 여러 조각이 나게 만든다.
    chunks = _chunk_text(text, "테스트", chunk_size=20, overlap=5)

    assert len(chunks) > 1


def test_every_chunk_is_tagged_with_chapter_title():
    # 검색 결과에서 "이 조각이 어느 챕터 소속인지" 알아야 하므로, 조각마다 접두사가 붙어야 한다.
    text = "첫 번째 문장입니다. 두 번째 문장입니다. 세 번째 문장입니다."
    chunks = _chunk_text(text, "법인카드 정산", chunk_size=15, overlap=3)

    assert len(chunks) > 1  # 여러 조각으로 나뉘었는지 먼저 확인 (안 나뉘면 아래 검증이 무의미)
    for chunk in chunks:
        assert chunk.startswith("[업무: 법인카드 정산]")


def test_overlap_repeats_tail_of_previous_chunk():
    # 조각 경계에서 문맥이 뚝 끊기지 않도록, 앞 조각의 마지막 overlap자가 다음 조각
    # 맨 앞에도 다시 나타나야 한다.
    text = "가나다라마바사아자차카타파하. 거너더러머버서어저처커터퍼허고."
    chunks = _chunk_text(text, "T", chunk_size=15, overlap=5)

    assert len(chunks) >= 2
    # 접두사("[업무: T] ")를 뗀 실제 본문끼리 비교
    first_body = chunks[0].removeprefix("[업무: T] ")
    second_body = chunks[1].removeprefix("[업무: T] ")
    tail_of_first = first_body[-5:]
    assert second_body.startswith(tail_of_first)


def test_empty_text_returns_no_chunks():
    chunks = _chunk_text("", "빈 챕터")

    assert chunks == []
