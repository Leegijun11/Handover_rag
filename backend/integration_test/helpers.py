# -*- coding: utf-8 -*-
"""통합 테스트 공용 도우미 (guidelines 5-10).

fixture가 아니라 일반 함수라서, 쓰려는 테스트 파일에서 직접 import해야 한다
(conftest.py의 fixture처럼 매개변수 이름만으로 자동 주입되지 않음).
"""

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

PASSWORD = "testpass123"


def unique_email(prefix: str) -> str:
    # 실행할 때마다 새 값이라 이전 테스트 실행이 남긴 데이터와 절대 안 겹친다
    # (실제 로컬 MySQL을 그대로 쓰므로 이게 없으면 "이미 가입된 이메일" 에러가 남).
    return f"{prefix}-{uuid.uuid4().hex[:10]}@itest.local"


def register_and_login(client: TestClient, name: str, role: str) -> dict:
    """회원가입 + 로그인을 한 번에. {token, user_id, email} 반환."""
    email = unique_email(name)
    register_resp = client.post(
        "/user/register",
        json={"name": name, "email": email, "password": PASSWORD, "role": role},
    )
    assert register_resp.status_code == 201, register_resp.text

    login_resp = client.post("/user/login", json={"email": email, "password": PASSWORD})
    assert login_resp.status_code == 200, login_resp.text

    return {
        "token": login_resp.json()["access_token"],
        "user_id": register_resp.json()["user_id"],
        "email": email,
    }


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_document_directly(mentor_id: str, label: str = "통합테스트 문서") -> str:
    """업로드 API(임베딩 호출 포함)를 거치지 않고, 배정 테스트에 필요한 최소 상태만
    DB에 직접 만든다 — 여기서 검증하려는 건 "문서가 잘 파싱/임베딩되는가"가 아니라
    "배정/권한 로직이 실제 DB 상태를 보고 올바르게 판단하는가"라서, 업로드 과정 자체는
    이 테스트의 관심사가 아니다 (이미 document 쪽 unit_test에서 따로 검증함).
    """
    from core.database import SessionLocal
    from models.document import DocumentMentorMapORM

    document_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        db.add(
            DocumentMentorMapORM(
                document_id=document_id,
                mentor_id=mentor_id,
                label=label,
                uploaded_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    finally:
        db.close()
    return document_id
