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
from models.document import DocumentChapterORM, DocumentMentorMapORM, list_documents_for_mentor
from schemas.document import DocumentChapter

router = APIRouter(tags=["document"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB (guidelines 5-9, 4-2)

# ── 임베딩 헬퍼 ──
EMBEDDING_MODEL = "text-embedding-3-small"  # 조장 core/llm.py의 EMBEDDING_MODEL과 동일 (4-2)
_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    # 모듈 import 시점에 바로 만들면 OPENAI_API_KEY가 없을 때 서버 부팅 자체가 실패함
    # (실제로 재현해서 발견 — .env에 키가 비어있으면 main.py의 라우터 import 단계에서
    # OpenAIError가 나서 서버가 아예 안 켜졌음). 첫 실제 사용 시점까지 생성을 미룸.
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def _embed_texts(texts: list[str]) -> list[list[float]]:
    response = _get_openai_client().embeddings.create(model=EMBEDDING_MODEL, input=texts)
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


def _parse_chapters_from_text(text: str, fallback_title: str = "전체 내용") -> list[dict]:
    """파일 본문에서 챕터 구조를 자동 인식. 실패하면 문서 전체를 챕터 1개로 폴백.

    인식 순서: 마크다운 헤더(#, ##) -> 숫자/장 넘버링 -> 둘 다 없으면 폴백.
    반환값 각 원소는 {"title": str, "content": str, "fallback": bool}.

    fallback_title: 목차를 못 찾았을 때 쓸 제목. 파일을 여러 개 올릴 때(아래
    upload_document) 전부 "전체 내용"이면 어느 파일이 폴백됐는지 구분이 안 되므로,
    호출부가 파일명을 넘겨서 구분되게 한다.
    """
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"'{fallback_title}' 파일 내용이 비어 있습니다")

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

    return [{"title": fallback_title, "content": text, "fallback": True}]


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
    label: str,
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

    db.add(DocumentMentorMapORM(document_id=document_id, mentor_id=mentor_id, label=label))
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


def _get_assignment(db: Session, newcomer_id: str):
    """models.assignment가 main에 merge되기 전에는 서버가 죽지 않도록 지연 import.
    아직 없으면 None 반환 (신입 배정 검증을 못 하는 상태로 취급, 사수 검증만 동작)."""
    try:
        from models.assignment import get_assignment_by_newcomer
    except ImportError:
        return None
    return get_assignment_by_newcomer(db, newcomer_id)


# ── API ──
@router.post("/document/upload", status_code=201)
async def upload_document(
    mentor_id: str = Form(...),
    files: list[UploadFile] | None = File(None),
    chapters: str | None = Form(None),  # JSON 문자열: [{"title": "...", "content": "..."}]
    label: str | None = Form(None),  # 목록 화면용 제목. 안 보내면 아래 기본 규칙으로 계산 (신설)
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """인수인계서 등록 (guidelines 3-2) — files 또는 chapters 중 정확히 하나만 받음.

    files는 여러 개를 보낼 수 있다 — 인수인계서가 파일 여러 개로 나뉘어 있는 경우를
    지원하기 위함(신설). 각 파일을 순서대로 독립적으로 자동 파싱해서, 그 결과 챕터를
    받은 순서 그대로 이어붙인다 — 파일 간 챕터 번호가 겹쳐도 chapter_id는 파일과
    무관하게 매번 새로 발급되므로 문제없다.

    label을 직접 입력하면 그 값을 그대로 쓰고, 비워두면 기존 기본 규칙(파일 모드는
    첫 파일명에서 확장자 제거, chapters 모드는 첫 챕터 제목)으로 계산한다. 수정 API는
    따로 안 둔다 — 문서 목록을 훑어보는 화면 자체가 없고(배정 화면 드롭다운에만
    쓰임), 잘못 지었으면 다시 올리는 게 더 단순하다.
    """
    require_role(current_user, "mentor")
    require_self(current_user, mentor_id)

    label_input = label.strip() if label else ""

    has_files = bool(files)
    if not has_files and chapters is None:
        raise HTTPException(status_code=400, detail="files 또는 chapters 중 하나는 필수입니다")
    if has_files and chapters is not None:
        raise HTTPException(status_code=400, detail="files와 chapters를 동시에 보낼 수 없습니다")

    if has_files:
        parsed_chapters: list[dict] = []
        for f in files:
            raw = await f.read()
            if len(raw) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400, detail=f"'{f.filename}' 파일 크기는 10MB를 초과할 수 없습니다"
                )
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{f.filename}'을 텍스트로 읽을 수 없습니다 (.txt, .md만 지원)",
                )
            fallback_title = f.filename.rsplit(".", 1)[0] if f.filename else "전체 내용"
            parsed_chapters.extend(_parse_chapters_from_text(text, fallback_title=fallback_title))
        # 목록 화면(GET /document)에 보여줄 대표 라벨. 문서에 제목 필드가 없어서(2-3)
        # 첫 파일명을 쓰고, 여러 개면 개수를 덧붙인다 — 프론트가 브라우저에만 임시로
        # 들고 있던 로직을 업로드 시점에 한 번만 계산해 DB에 고정하는 것으로 옮김.
        # 확장자(.md/.txt)는 목록에서 굳이 안 보여도 되는 정보라 잘라낸다 —
        # fallback_title과 같은 rsplit 규칙을 써서 두 값이 서로 어긋나지 않게 한다.
        first_name_raw = files[0].filename or "제목 없는 인수인계서"
        first_name = first_name_raw.rsplit(".", 1)[0] if "." in first_name_raw else first_name_raw
        default_label = first_name if len(files) == 1 else f"{first_name} 외 {len(files) - 1}개"
    else:
        parsed_chapters = _parse_chapters_json(chapters)
        default_label = parsed_chapters[0]["title"] if parsed_chapters else "제목 없는 인수인계서"

    final_label = label_input or default_label

    document_id = str(uuid.uuid4())
    chapter_rows = _save_and_index_chapters(db, document_id, mentor_id, parsed_chapters, final_label)

    return {"document_id": document_id, "chapters": _chapters_to_response(document_id, chapter_rows)}


@router.get("/document")
def list_documents(
    mentor_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """이 사수가 올린 문서 목록, 최신순 (guidelines 3-2 신설 — 배정 화면 드롭다운용).

    기존엔 이 목록을 프론트 브라우저의 localStorage로만 임시 관리해서 다른 브라우저/
    기기에서는 안 보이는 문제가 있었음(api/documentHistory.js) — DB 기반으로 교체.
    """
    require_role(current_user, "mentor")
    require_self(current_user, mentor_id)

    rows = list_documents_for_mentor(db, mentor_id)
    return [
        {"document_id": r.document_id, "label": r.label, "uploaded_at": r.uploaded_at}
        for r in rows
    ]


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

    assignment = _get_assignment(db, current_user["user_id"])
    is_assigned_newcomer = (
        assignment is not None and assignment.document_id == document_id
    )

    if not (is_owner_mentor or is_assigned_newcomer):
        raise HTTPException(status_code=403, detail="권한이 없습니다")

    rows = (
        db.query(DocumentChapterORM)
        .filter(DocumentChapterORM.document_id == document_id)
        .all()
    )
    return _chapters_to_response(document_id, rows)