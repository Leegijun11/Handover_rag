from pydantic import BaseModel


class Assignment(BaseModel):
    assignment_id: str
    newcomer_id: str  # User.user_id (role="newcomer")
    mentor_id: str  # User.user_id (role="mentor")
    document_id: str  # 이 신입에게 배정된 인수인계서
