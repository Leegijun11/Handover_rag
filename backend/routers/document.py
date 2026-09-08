"""문서 처리 (담당: 팀원 A) — guidelines 3-2, 3-9, 4-2."""

import os
import re
import uuid

from fastapi import APIRouter, Depends
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import CurrentUser, get_current_user, require_role, require_self
from core.chroma_client import get_collection
from core.database import get_db
from models.document import DocumentChapterORM, DocumentMentorMapORM
from schemas.document import DocumentChapter

router = APIRouter(tags=["document"])


# ── 임베딩 헬퍼 ──
# TODO(A): 조장과 임베딩 모델 확정되면 이 값만 교체
EMBEDDING_MODEL = "text-embedding-3-small"
_openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _embed_texts(texts: list[str]) -> list[list[float]]:
    response = _openai_client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


# ── 청킹 헬퍼 (문장경계 존중 + 오버랩 + 챕터제목 prefix) ──
def _chunk_text(text: str, chapter_title: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    chunks = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) <= chunk_size:
            current += (" " if current else "") + sentence
        else:
            if current:
                chunks.append(f"[챕터: {chapter_title}] {current}")
            overlap_text = current[-overlap:] if len(current) > overlap else current
            current = overlap_text + " " + sentence

    if current:
        chunks.append(f"[챕터: {chapter_title}] {current}")

    return chunks


# ── 요청 스키마 ──
class ChapterInput(BaseModel):
    title: str
    content: str


class UploadChaptersRequest(BaseModel):
    mentor_id: str
    chapters: list[ChapterInput]


# ── API ──
@router.post("/document/upload", status_code=201)
def upload_document(
    payload: UploadChaptersRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")
    require_self(current_user, payload.mentor_id)

    document_id = str(uuid.uuid4())

    # 1. 챕터 저장 (파싱 없이 그대로 — 직접입력 경로)
    chapter_rows = []
    for ch in payload.chapters:
        row = DocumentChapterORM(
            chapter_id=str(uuid.uuid4()),
            document_id=document_id,
            title=ch.title,
            parent_id=None,
            content=ch.content,
        )
        db.add(row)
        chapter_rows.append(row)

    # 2. document -> mentor 매핑 기록
    db.add(DocumentMentorMapORM(document_id=document_id, mentor_id=payload.mentor_id))
    db.commit()

    # 3~4. 챕터별 청킹 -> 임베딩 -> ChromaDB 저장
    collection = get_collection(document_id)
    for row in chapter_rows:
        pieces = _chunk_text(row.content, row.title)
        vectors = _embed_texts(pieces)
        chunk_ids = [str(uuid.uuid4()) for _ in pieces]  # DocumentChunk.chunk_id
        collection.add(
            ids=chunk_ids,
            embeddings=vectors,
            documents=pieces,
            metadatas=[
                {"document_id": document_id, "chapter_id": row.chapter_id, "fallback": False}
                for _ in pieces
            ],
        )

    chapters_response = [
        DocumentChapter(
            chapter_id=r.chapter_id,
            document_id=document_id,
            title=r.title,
            parent_id=r.parent_id,
            content=r.content,
        )
        for r in chapter_rows
    ]
    return {"document_id": document_id, "chapters": chapters_response}