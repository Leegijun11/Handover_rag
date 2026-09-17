# -*- coding: utf-8 -*-
"""GET /document/{document_id}/chapters 권한 검증 (guidelines 3-9).

report.py/chat.py에서 찾아서 고친 것과 같은 종류의 규칙 — "이 문서를 업로드한
사수" 또는 "이 문서로 배정받은 신입"만 챕터 본문(인수인계서 내용 그 자체)을
볼 수 있어야 한다. 이 엔드포인트는 그동안 자동화된 테스트가 한 번도 없었다.
"""

from helpers import auth_headers, create_document_directly, register_and_login


def _assign(client, mentor, newcomer, document_id):
    resp = client.post(
        "/assignment",
        json={"mentor_id": mentor["user_id"], "newcomer_id": newcomer["user_id"], "document_id": document_id},
        headers=auth_headers(mentor["token"]),
    )
    assert resp.status_code == 201, resp.text
    return resp


def test_owner_mentor_can_read_chapters(client):
    mentor = register_and_login(client, "문서주인사수", "mentor")
    document_id = create_document_directly(mentor["user_id"])

    resp = client.get(f"/document/{document_id}/chapters", headers=auth_headers(mentor["token"]))

    assert resp.status_code == 200


def test_assigned_newcomer_can_read_chapters(client):
    mentor = register_and_login(client, "배정사수", "mentor")
    newcomer = register_and_login(client, "배정신입", "newcomer")
    document_id = create_document_directly(mentor["user_id"])
    _assign(client, mentor, newcomer, document_id)

    resp = client.get(f"/document/{document_id}/chapters", headers=auth_headers(newcomer["token"]))

    assert resp.status_code == 200


def test_unrelated_mentor_cannot_read_chapters(client):
    owner_mentor = register_and_login(client, "진짜주인사수", "mentor")
    other_mentor = register_and_login(client, "무관한사수", "mentor")
    document_id = create_document_directly(owner_mentor["user_id"])

    resp = client.get(f"/document/{document_id}/chapters", headers=auth_headers(other_mentor["token"]))

    assert resp.status_code == 403


def test_unassigned_newcomer_cannot_read_chapters(client):
    mentor = register_and_login(client, "문서사수2", "mentor")
    document_id = create_document_directly(mentor["user_id"])
    unrelated_newcomer = register_and_login(client, "배정안된신입", "newcomer")
    # 이 신입은 배정 자체를 아예 받은 적이 없는 상태 (Assignment 행이 없음)

    resp = client.get(f"/document/{document_id}/chapters", headers=auth_headers(unrelated_newcomer["token"]))

    assert resp.status_code == 403


def test_newcomer_assigned_to_a_different_document_cannot_read_this_one(client):
    # "배정 자체가 없는" 경우 말고, "다른 문서로는 배정받았지만 이 문서는 아닌" 경우까지
    # 막히는지 확인 — is_assigned_newcomer가 document_id까지 정확히 비교하는지가 핵심.
    mentor = register_and_login(client, "문서사수3", "mentor")
    newcomer = register_and_login(client, "다른문서신입", "newcomer")
    target_document_id = create_document_directly(mentor["user_id"], label="진짜 문서")
    other_document_id = create_document_directly(mentor["user_id"], label="다른 문서")
    _assign(client, mentor, newcomer, other_document_id)  # target_document_id가 아니라 다른 문서로 배정

    resp = client.get(f"/document/{target_document_id}/chapters", headers=auth_headers(newcomer["token"]))

    assert resp.status_code == 403
