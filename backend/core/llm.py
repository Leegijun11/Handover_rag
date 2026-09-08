"""OpenAI 클라이언트 공용 헬퍼 (담당: 조장) — chat.py/checklist_draft.py/report.py가 공유.

모든 호출에 max_completion_tokens 상한을 강제한다 (guidelines 5-9 항목 3).

임베딩 모델 고정: EMBEDDING_MODEL은 챗봇 검색(chat.py)이 쓰는 값이고, 팀원 A의
문서 청킹·임베딩 저장 파이프라인(document.py)도 반드시 같은 모델을 써야 한다 —
저장할 때와 검색할 때 임베딩 모델이 다르면 벡터 공간이 안 맞아서 검색 결과가
전부 무의미해짐 (guidelines 4-2에 이 요구사항 반영해둠).
"""

import os

from openai import OpenAI

_client: OpenAI | None = None

CHAT_MODEL = "gpt-4o-mini"
DRAFT_MODEL = "gpt-4o-mini"  # 정확도보다 비용 우선 (guidelines 5-9 항목 3)
REPORT_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

DEFAULT_MAX_TOKENS = 500


def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def chat_complete(
    system_prompt: str,
    user_prompt: str,
    model: str = CHAT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """단순 1턴 completion 헬퍼. max_completion_tokens 상한 항상 적용 (5-9)."""
    client = get_openai_client()
    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""


def embed_text(text: str, model: str = EMBEDDING_MODEL) -> list[float]:
    client = get_openai_client()
    response = client.embeddings.create(model=model, input=text)
    return response.data[0].embedding
