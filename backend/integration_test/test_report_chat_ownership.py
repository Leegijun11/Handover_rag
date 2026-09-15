# -*- coding: utf-8 -*-
"""다른 사수가 남의 신입 리포트/챗로그를 못 보는지 — 9/13에 발견해서 고친 보안
회귀 방지용 (guidelines 5-10). 그때는 curl로 손으로 확인했는데, 여기서 자동화해서
나중에 누가 이 검증 코드를 실수로 건드려도 바로 잡히게 한다.

DocumentMentorMapORM은 helpers.create_document_directly()로 DB에 직접 만든다 —
/document/upload를 거치면 실제 임베딩 호출까지 필요해지는데, 여기서 검증하려는 건
"업로드가 되는가"가 아니라 "권한 검증이 실제 DB 상태를 보고 맞게 판단하는가"라서다.
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


def test_other_mentor_cannot_generate_report_for_someone_elses_newcomer(client):
    mentor_a = register_and_login(client, "사수A", "mentor")
    mentor_b = register_and_login(client, "사수B", "mentor")
    newcomer = register_and_login(client, "신입", "newcomer")

    document_id = create_document_directly(mentor_a["user_id"])
    _assign(client, mentor_a, newcomer, document_id)

    # 담당이 아닌 사수 B가 신입의 리포트를 생성하려고 시도
    resp = client.post(
        "/report/generate",
        json={"newcomer_id": newcomer["user_id"]},
        headers=auth_headers(mentor_b["token"]),
    )

    assert resp.status_code == 403


def test_other_mentor_cannot_read_report_or_history(client):
    mentor_a = register_and_login(client, "사수A리포트", "mentor")
    mentor_b = register_and_login(client, "사수B리포트", "mentor")
    newcomer = register_and_login(client, "신입리포트", "newcomer")

    document_id = create_document_directly(mentor_a["user_id"])
    _assign(client, mentor_a, newcomer, document_id)

    assert client.get(
        f"/report/{newcomer['user_id']}", headers=auth_headers(mentor_b["token"])
    ).status_code == 403
    assert client.get(
        f"/report/{newcomer['user_id']}/history", headers=auth_headers(mentor_b["token"])
    ).status_code == 403


def test_other_mentor_cannot_read_chat_logs(client):
    mentor_a = register_and_login(client, "사수A챗로그", "mentor")
    mentor_b = register_and_login(client, "사수B챗로그", "mentor")
    newcomer = register_and_login(client, "신입챗로그", "newcomer")

    document_id = create_document_directly(mentor_a["user_id"])
    _assign(client, mentor_a, newcomer, document_id)

    resp = client.get(
        f"/chat/logs?newcomer_id={newcomer['user_id']}", headers=auth_headers(mentor_b["token"])
    )

    assert resp.status_code == 403


def test_owning_mentor_can_generate_and_read_report(client, monkeypatch):
    # OpenAI 요약 호출만 mock — 반복 실행해도 비용/속도 부담이 없게.
    monkeypatch.setattr("routers.report.chat_complete", lambda **kwargs: "요약 텍스트")

    mentor = register_and_login(client, "진짜담당사수", "mentor")
    newcomer = register_and_login(client, "진짜담당신입", "newcomer")

    document_id = create_document_directly(mentor["user_id"])
    _assign(client, mentor, newcomer, document_id)

    generate_resp = client.post(
        "/report/generate",
        json={"newcomer_id": newcomer["user_id"]},
        headers=auth_headers(mentor["token"]),
    )
    assert generate_resp.status_code == 200
    assert len(generate_resp.json()["sections"]) == 4

    read_resp = client.get(f"/report/{newcomer['user_id']}", headers=auth_headers(mentor["token"]))
    assert read_resp.status_code == 200
