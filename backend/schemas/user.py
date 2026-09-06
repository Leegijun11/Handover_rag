from typing import Literal

from pydantic import BaseModel


class User(BaseModel):
    user_id: str
    name: str
    email: str
    password_hash: str
    role: Literal["newcomer", "mentor"]


class UserPublic(BaseModel):
    """API 응답용 — password_hash 제외 (guidelines 2-1)."""

    user_id: str
    name: str
    email: str
    role: Literal["newcomer", "mentor"]
