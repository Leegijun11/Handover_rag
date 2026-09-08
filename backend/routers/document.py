"""문서 처리 (담당: 팀원 A) — guidelines 3-2, 3-9, 4-2."""

import json
import os
import re
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from core.auth import CurrentUser, get_current_user, require_role, require_self
from core.chroma_client import get_collection
from core.database import get_db
from models.document import DocumentChapterORM, DocumentMentorMapORM
from schemas.document import DocumentChapter

router = APIRouter(tags=["document"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB (guidelines 5-9, 4-2)

# ── 임베딩 헬퍼 ──
EMBEDDING_MODEL = "text-embedding-3-small"  # 조장 core/llm.py의 EMBEDDING_MODEL과 동일 (4-2)
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


# ── 파일 자동파싱 헬퍼 ──
_MD_HEADER_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^((?:\d+[-.])+\d*\.?|제\s*\d+\s*장)\s*(.+)$", re.MULTILINE)


def _parse_chapters_from_text(text: str) -> list[dict]:
    """파일 본문에서 챕터 구조를 자동 인식. 실패하면 문서 전체를 챕터 1개로 폴백.

    인식 순서: 마크다운 헤더(#, ##) -> 숫자/장 넘버링 -> 둘 다 없으면 폴백.
    반환값 각 원소는 {"title": str, "content": str, "fallback": bool}.
    """
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="파일 내용이 비어 있습니다")

    for pattern in (_MD_HEADER_RE, _NUMBERED_RE):
        matches = list(pattern.finditer(text))
        if len(matches) >= 2:
            chapters = []
            for i, m in enumerate(matches):
                title = m.group(2).strip()
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                content = text[start:end].strip()
                if content:
                    chapters.append({"title": title, "content": content, "fallback": False})
            if chapters:
                return chapters

    return [{"title": "전체 내용", "content": text, "fallback": True}]


class ChapterInput(BaseModel):
    title: str
    content: str


def _parse_chapters_json(chapters_raw: str) -> list[dict]:
    """chapters 폼 필드(JSON 문자열)를 파싱·검증. 실패하면 400."""
    try:
        raw_list = json.loads(chapters_raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="chapters는 올바른 JSON 형식이어야 합니다")

    try:
        validated = [ChapterInput(**item) for item in raw_list]
    except (ValidationError, TypeError):
        raise HTTPException(status_code=400, detail="chapters 형식이 올바르지 않습니다 (title, content 필요)")

    return [{"title": c.title, "content": c.content} for c in validated]


def _save_and_index_chapters(
    db: Session,
    document_id: str,
    mentor_id: str,
    chapters: list[dict],
) -> list[DocumentChapterORM]:
    """챕터 저장 + mentor 매핑 기록 + 청킹->임베딩->ChromaDB 저장 (두 입력방식 공용)."""
    chapter_rows = []
    for ch in chapters:
        row = DocumentChapterORM(
            chapter_id=str(uuid.uuid4()),
            document_id=document_id,
            title=ch["title"],
            parent_id=None,
            content=ch["content"],
        )
        db.add(row)
        chapter_rows.append(row)

    db.add(DocumentMentorMapORM(document_id=document_id, mentor_id=mentor_id))
    db.commit()

    collection = get_collection(document_id)
    for row, ch in zip(chapter_rows, chapters):
        pieces = _chunk_text(row.content, row.title)
        vectors = _embed_texts(pieces)
        chunk_ids = [str(uuid.uuid4()) for _ in pieces]
        collection.add(
            ids=chunk_ids,
            embeddings=vectors,
            documents=pieces,
            metadatas=[
                {
                    "document_id": document_id,
                    "chapter_id": row.chapter_id,
                    "fallback": ch.get("fallback", False),
                }
                for _ in pieces
            ],
        )
    return chapter_rows


def _chapters_to_response(document_id: str, rows: list[DocumentChapterORM]) -> list[DocumentChapter]:
    return [
        DocumentChapter(
            chapter_id=r.chapter_id,
            document_id=document_id,
            title=r.title,
            parent_id=r.parent_id,
            content=r.content,
        )
        for r in rows
    ]


# ── API ──
@router.post("/document/upload", status_code=201)
async def upload_document(
    mentor_id: str = Form(...),
    file: UploadFile | None = File(None),
    chapters: str | None = Form(None),  # JSON 문자열: [{"title": "...", "content": "..."}]
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """인수인계서 등록 (guidelines 3-2) — file 또는 chapters 중 정확히 하나만 받음."""
    require_role(current_user, "mentor")
    require_self(current_user, mentor_id)

    if file is None and chapters is None:
        raise HTTPException(status_code=400, detail="file 또는 chapters 중 하나는 필수입니다")
    if file is not None and chapters is not None:
        raise HTTPException(status_code=400, detail="file과 chapters를 동시에 보낼 수 없습니다")

    if file is not None:
        raw = await file.read()
        if len(raw) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="파일 크기는 10MB를 초과할 수 없습니다")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="텍스트로 읽을 수 없는 파일입니다 (.txt, .md만 지원)")
        parsed_chapters = _parse_chapters_from_text(text)
    else:
        parsed_chapters = _parse_chapters_json(chapters)

    document_id = str(uuid.uuid4())
    chapter_rows = _save_and_index_chapters(db, document_id, mentor_id, parsed_chapters)

    return {"document_id": document_id, "chapters": _chapters_to_response(document_id, chapter_rows)}


@router.get("/document/{document_id}/chapters")
def get_chapters(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mapping = (
        db.query(DocumentMentorMapORM)
        .filter(DocumentMentorMapORM.document_id == document_id)
        .first()
    )
    is_owner_mentor = mapping is not None and mapping.mentor_id == current_user["user_id"]

    # TODO(A, B와 협의): 배정된 신입인지 확인 — Assignment 조회 준비되면 추가

    if not is_owner_mentor:
        raise HTTPException(status_code=403, detail="권한이 없습니다")

    rows = (
        db.query(DocumentChapterORM)
        .filter(DocumentChapterORM.document_id == document_id)
        .all()
    )
    return _chapters_to_response(document_id, rows)