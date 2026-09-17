# -*- coding: utf-8 -*-
"""재배정해도 assignment_id/assigned_at이 그대로 유지되는지 (guidelines 2-2, 3-1).

/report/generate가 최초 리포트의 period_start 기본값으로 assigned_at을 쓰기 때문에,
재배정마다 이 값이 갱신되면 리포트 기간이 매번 리셋되는 실제 버그가 된다 — 이건
DB에 실제로 UPDATE가 일어나는 동작이라 mock으로는 검증이 안 되고, 진짜 DB에 붙는
통합 테스트가 필요한 대표적인 경우.
"""

from helpers import auth_headers, create_document_directly, register_and_login


def test_reassignment_keeps_assignment_id_and_assigned_at(client):
    mentor = register_and_login(client, "재배정사수", "mentor")
    newcomer = register_and_login(client, "재배정신입", "newcomer")

    doc_a = create_document_directly(mentor["user_id"], label="문서 A")
    doc_b = create_document_directly(mentor["user_id"], label="문서 B")

    first = client.post(
        "/assignment",
        json={"mentor_id": mentor["user_id"], "newcomer_id": newcomer["user_id"], "document_id": doc_a},
        headers=auth_headers(mentor["token"]),
    )
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["document_id"] == doc_a

    # 같은 신입에게 다른 문서로 재배정
    second = client.post(
        "/assignment",
        json={"mentor_id": mentor["user_id"], "newcomer_id": newcomer["user_id"], "document_id": doc_b},
        headers=auth_headers(mentor["token"]),
    )
    assert second.status_code == 201
    second_body = second.json()

    # 문서는 바뀌었지만, 배정 자체는 "같은 배정"이어야 한다 (새 행이 아니라 갱신)
    assert second_body["document_id"] == doc_b
    assert second_body["assignment_id"] == first_body["assignment_id"]
    assert second_body["assigned_at"] == first_body["assigned_at"]


def test_reassignment_by_different_mentor_is_rejected(client):
    # 재배정 규칙은 "document_id만 교체"이지 담당 사수를 바꾸는 게 아니다 —
    # 다른 사수가 남의 담당 신입을 가로채려는 시도는 막혀야 한다.
    mentor_a = register_and_login(client, "원래사수", "mentor")
    mentor_b = register_and_login(client, "다른사수", "mentor")
    newcomer = register_and_login(client, "가로채기대상신입", "newcomer")

    doc_a = create_document_directly(mentor_a["user_id"])
    doc_b = create_document_directly(mentor_b["user_id"])

    first = client.post(
        "/assignment",
        json={"mentor_id": mentor_a["user_id"], "newcomer_id": newcomer["user_id"], "document_id": doc_a},
        headers=auth_headers(mentor_a["token"]),
    )
    assert first.status_code == 201

    hijack = client.post(
        "/assignment",
        json={"mentor_id": mentor_b["user_id"], "newcomer_id": newcomer["user_id"], "document_id": doc_b},
        headers=auth_headers(mentor_b["token"]),
    )

    assert hijack.status_code == 403
