"""체크리스트 초안 생성 (담당: 조장) — guidelines 3-4, 3-9, 4-1, 5-9, 1-5.

핵심 흐름:
  1. document_id에 해당하는 DocumentChapter를 MySQL에서 조회 (ChromaDB 접근 금지 — guidelines 1-5)
  2. 챕터를 순회하며 LLM으로 태스크 후보 {title, chapter_id} 생성
  3. 저장하지 않고 리스트만 반환 (미리보기 — 실제 저장은 팀원 A의 POST /checklist)
"""

import json
from typing import TypedDict

from fastapi import APIRouter, Depends, Request
from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import CurrentUser, get_current_user, require_role
from core.database import get_db
from core.llm import DRAFT_MODEL, chat_complete
from core.rate_limit import IP_RATE_LIMIT, USER_RATE_LIMIT, ip_limiter, user_limiter
from models.document import DocumentChapterORM

router = APIRouter(tags=["checklist_draft"])


class DraftRequest(BaseModel):
    document_id: str


def _get_chapters(db: Session, document_id: str) -> list[dict]:
    rows = db.query(DocumentChapterORM).filter_by(document_id=document_id).all()
    return [{"chapter_id": r.chapter_id, "title": r.title, "content": r.content} for r in rows]


class DraftState(TypedDict):
    document_id: str
    chapters: list[dict]
    items: list[dict]


def _make_load_chapters_node(db: Session):
    def _node(state: DraftState) -> DraftState:
        state["chapters"] = _get_chapters(db, state["document_id"])
        return state

    return _node


def _node_generate_tasks(state: DraftState) -> DraftState:
    items: list[dict] = []
    for chapter in state["chapters"]:
        # 순수 그룹핑용 상위 챕터(content=None)는 건너뜀 — LLM에 넘길 내용이 없음
        # (guidelines 2-3, content 필드가 null 허용으로 바뀐 이유 참고)
        if not chapter.get("content"):
            continue
        raw = chat_complete(
            system_prompt=(
                "너는 신입사원 온보딩 체크리스트를 설계하는 사수다. 주어진 인수인계서 챕터를 "
                "읽고, 신입이 실제로 해봐야 할 구체적인 태스크를 1~3개 뽑아라. "
                '반드시 JSON 배열로만 답하라. 예: ["작업 A 해보기", "작업 B 확인하기"]'
            ),
            user_prompt=f"[챕터: {chapter['title']}]\n{chapter['content']}",
            model=DRAFT_MODEL,
        )
        try:
            titles = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            titles = []
        for title in titles:
            if isinstance(title, str):
                items.append({"title": title, "chapter_id": chapter["chapter_id"]})
    state["items"] = items
    return state


def _build_graph(db: Session):
    graph = StateGraph(DraftState)
    graph.add_node("load_chapters", _make_load_chapters_node(db))
    graph.add_node("generate_tasks", _node_generate_tasks)
    graph.set_entry_point("load_chapters")
    graph.add_edge("load_chapters", "generate_tasks")
    graph.add_edge("generate_tasks", END)
    return graph.compile()


@router.post("/checklist/draft")
@user_limiter.limit(USER_RATE_LIMIT)
@ip_limiter.limit(IP_RATE_LIMIT)
def draft_checklist(
    request: Request,
    payload: DraftRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "mentor")

    graph = _build_graph(db)
    result = graph.invoke({"document_id": payload.document_id, "chapters": [], "items": []})
    return result["items"]
