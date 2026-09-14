# -*- coding: utf-8 -*-
"""routers/user.py의 RegisterRequest 검증 테스트 (guidelines 5-10).

주의: "이메일 형식 검증"이지 "이메일 인증"(실제 메일 발송으로 소유주 확인)이 아니다.
후자는 guidelines 6-5에 따라 2차 확장 항목으로 미뤄져 있고 지금은 구현 안 됨 — 여기서
테스트하는 건 그냥 "xxx@yyy.zzz 모양을 갖췄는지"만 보는, 이미 구현된 순수 검증 로직.
"""

import pytest
from pydantic import ValidationError

from routers.user import RegisterRequest

VALID = dict(name="김철수", email="test@example.com", password="testpass123", role="newcomer")


def test_valid_payload_is_accepted():
    req = RegisterRequest(**VALID)

    assert req.email == "test@example.com"


def test_email_is_lowercased_and_trimmed():
    # 대소문자만 다른 중복 가입을 막으려고 저장 전에 소문자로 통일한다.
    req = RegisterRequest(**{**VALID, "email": "  Test@Example.COM  "})

    assert req.email == "test@example.com"


def test_email_without_at_sign_is_rejected():
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "email": "not-an-email"})


def test_email_without_domain_dot_is_rejected():
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "email": "test@localhost"})


def test_email_with_space_is_rejected():
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "email": "test @example.com"})


def test_password_shorter_than_8_chars_is_rejected():
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "password": "short1"})


def test_password_within_byte_limit_is_accepted():
    # 한글은 글자당 3바이트 -> 24자면 72바이트로 딱 걸림 (경계값)
    req = RegisterRequest(**{**VALID, "password": "가" * 24})

    assert len(req.password.encode("utf-8")) == 72


def test_password_over_byte_limit_is_rejected():
    # 25자(=75바이트)부터는 bcrypt 72바이트 상한을 넘어서 거부돼야 한다.
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "password": "가" * 25})


def test_invalid_role_is_rejected():
    with pytest.raises(ValidationError):
        RegisterRequest(**{**VALID, "role": "admin"})  # newcomer/mentor 외 값
