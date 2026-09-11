"""User 테이블 (담당: LeeJongHoon) — schemas/user.py와 1:1 (guidelines 5-3-1)."""

import uuid

from sqlalchemy import Column, String

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class UserORM(Base):
    __tablename__ = "users"

    user_id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(100), nullable=False)
    # 로그인 식별자. 인증 메일 발송은 2차 확장 항목이고, 1차에서는 중복 가입만
    # 막으면 되므로 unique 제약으로 처리한다 (guidelines 2-1, 6-5).
    # 길이 255는 이메일 주소의 통상 상한(RFC 5321 기준 254)에 맞춘 값.
    email = Column(String(255), unique=True, nullable=False)
    # bcrypt 해시는 60자지만, 알고리즘이 바뀌어도 스키마를 안 건드리도록 여유를 둔다.
    # 평문은 저장하지 않으며 이 값은 API 응답에 절대 포함하지 않는다 (guidelines 2-1).
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)  # newcomer / mentor
