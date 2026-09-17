# -*- coding: utf-8 -*-
"""회원가입 -> 로그인 -> 내 정보 조회, 실제 로컬 MySQL에 그대로 붙여서 확인 (guidelines 5-10).

unit_test의 mock 테스트들과 다른 점: 여기는 DB를 가짜로 안 만들고, 진짜
core/auth.py(비밀번호 해싱, JWT)와 진짜 MySQL 저장/조회까지 전부 실제로 탄다.
OpenAI를 안 건드리는 흐름이라 mock도 전혀 필요 없다.
"""

from helpers import auth_headers, register_and_login


def test_register_login_and_fetch_own_profile(client):
    user = register_and_login(client, "통합테스트유저", "newcomer")

    resp = client.get(f"/user/{user['user_id']}", headers=auth_headers(user["token"]))

    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == user["email"]
    assert body["role"] == "newcomer"
    assert "password_hash" not in body  # 절대 응답에 노출되면 안 되는 필드 (guidelines 2-1)


def test_wrong_password_is_rejected(client):
    user = register_and_login(client, "로그인테스트", "newcomer")

    resp = client.post("/user/login", json={"email": user["email"], "password": "틀린비밀번호999"})

    assert resp.status_code == 401


def test_request_without_token_is_rejected(client):
    user = register_and_login(client, "무토큰테스트", "newcomer")

    resp = client.get(f"/user/{user['user_id']}")  # Authorization 헤더를 아예 안 보냄

    assert resp.status_code == 401
