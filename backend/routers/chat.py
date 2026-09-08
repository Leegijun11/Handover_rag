"""챗봇 RAG (담당: 조장) — guidelines 3-3, 3-9, 4-1, 5-9.

핵심 흐름 (LangGraph 그래프):
  1. 조회: newcomer_id로 Assignment 조회 -> document_id 확정 (Assignment 없으면 404)
  2. 검색: document_id 범위로 ChromaDB 검색
  3. 판단: 검색 결과 유사도가 충분한지 판단
  4. 생성: 충분하면 OpenAI로 답변 생성 + matched_chapter_id 기록,
     부족하면 answered=False + 고정 문구 ("문서에 없는 내용이니 담당자에게 문의하세요")
     — 이 시점에 "문서 보강" 언급 절대 금지 (guidelines 1-7, 4-1)
  5. 저장: ChatLog 생성 (question_type 분류 포함)

TODO(연동 필요 — 팀원 B): Assignment 조회(_get_assignment_document_id)가 스텁입니다.
팀원 B의 feature 브랜치가 main에 병합되어 models/assignment.py가 생기면,
아래 함수 안의 주석 처리된 실제 쿼리로 교체하세요. 지금은 항상 배정 없음(None)으로
동작해서 /chat/ask가 항상 404를 반환합니다 — 이게 정상 동작입니다(미연동 상태의 안전한 기본값).
"""

import uuid
from datetime import datetime, timezone
from typing import Literal, TypedDict

from fastapi import APIRouter, Depends, HTTPException, Request
from langgraph.graph import END, StateGraph
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import CurrentUser, get_current_user, require_self
from core.chroma_client import get_collection
from core.database import get_db
from core.llm import chat_complete, embed_text
from core.rate_limit import IP_RATE_LIMIT, USER_RATE_LIMIT, ip_limiter, user_limiter
from models.chat import ChatLogORM
from schemas.chat import ChatLog

router = APIRouter(tags=["chat"])

NO_ANSWER_MESSAGE = "문서에 없는 내용이니 담당자에게 문의하세요."
# ChromaDB 거리 기준 임계값(코사인 거리, 낮을수록 유사). 실측하며 조정 (재량).
# TODO(3개 브랜치 병합 후 실측 — guidelines 6-7): 이 값 조정과 함께, 1위 vs 2위·3위
# distance 차이가 유의미한지도 같이 측정할 것. 차이가 흔히 미미하면 matched_chapter_id를
# 단일값 대신 복수 챕터로 바꾸는 걸 검토 (스키마 변경 필요 — 6-7 참고).
SIMILARITY_THRESHOLD = 0.75


class AskRequest(BaseModel):
    newcomer_id: str
    question: str


def _get_assignment_document_id(db: Session, newcomer_id: str) -> str | None:
    """TODO(연동 필요 — 팀원 B): models/assignment.py 병합 후 아래 실제 쿼리로 교체.

        from models.assignment import AssignmentORM
        row = db.query(AssignmentORM).filter_by(newcomer_id=newcomer_id).first()
        return row.document_id if row else None

    지금은 팀원 B 브랜치가 main에 없어 조회 불가 — None(배정 없음 취급) 반환.
    """
    return None


class ChatState(TypedDict):
    newcomer_id: str
    question: str
    document_id: str
    search_results: list[dict]
    answered: bool
    answer: str
    matched_chapter_id: str | None
    question_type: Literal["fact", "procedure", "judgment", "advanced"]


def _classify_question_type(question: str) -> Literal["fact", "procedure", "judgment", "advanced"]:
    result = chat_complete(
        system_prompt=(
            "질문을 fact/procedure/judgment/advanced 중 하나로만 분류해라. "
            "다른 말은 절대 하지 말고 그 단어 하나만 출력해라."
        ),
        user_prompt=question,
        max_tokens=10,
    )
    normalized = result.strip().lower()
    if normalized in ("fact", "procedure", "judgment", "advanced"):
        return normalized  # type: ignore[return-value]
    return "fact"


def _node_search(state: ChatState) -> ChatState:
    collection = get_collection(state["document_id"])
    # 임베딩 모델은 core/llm.py의 EMBEDDING_MODEL 고정값 — 팀원 A의 저장 파이프라인도
    # 반드시 같은 모델을 써야 검색이 맞음 (core/llm.py 상단 설명, guidelines 4-2 참고).
    query_embedding = embed_text(state["question"])
    result = collection.query(query_embeddings=[query_embedding], n_results=3)

    hits: list[dict] = []
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        hits.append({"text": doc, "chapter_id": (meta or {}).get("chapter_id"), "distance": dist})
    state["search_results"] = hits
    return state


def _node_judge(state: ChatState) -> ChatState:
    hits = state["search_results"]
    state["answered"] = bool(hits) and hits[0]["distance"] <= SIMILARITY_THRESHOLD
    return state


def _node_generate(state: ChatState) -> ChatState:
    if state["answered"]:
        context = "\n\n".join(h["text"] for h in state["search_results"])
        state["answer"] = chat_complete(
            system_prompt=(
                "너는 신입사원 온보딩을 돕는 사내 챗봇이다. 아래 인수인계서 발췌 내용만 근거로 "
                "간결하고 정확하게 답변하라. 발췌에 없는 내용은 추측하지 마라."
            ),
            user_prompt=f"[인수인계서 발췌]\n{context}\n\n[질문]\n{state['question']}",
        )
        state["matched_chapter_id"] = state["search_results"][0]["chapter_id"]
    else:
        state["answer"] = NO_ANSWER_MESSAGE
        # TODO(연동 필요 — 팀원 A): 4-1 요구사항은 "실패 시 챕터 제목 목록 중 LLM이
        # 근접 추정"을 요구하지만, 챕터 제목 목록을 얻으려면 DocumentChapter 조회가
        # 필요함(팀원 A 미병합). 지금은 "추정도 어려우면 None" 폴백으로 처리.
        state["matched_chapter_id"] = None

    state["question_type"] = _classify_question_type(state["question"])
    return state


def _make_save_node(db: Session):
    def _node_save(state: ChatState) -> ChatState:
        db.add(
            ChatLogORM(
                log_id=str(uuid.uuid4()),
                newcomer_id=state["newcomer_id"],
                question=state["question"],
                answered=state["answered"],
                matched_chapter_id=state["matched_chapter_id"],
                question_type=state["question_type"],
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return state

    return _node_save


def _build_graph(db: Session):
    graph = StateGraph(ChatState)
    graph.add_node("search", _node_search)
    graph.add_node("judge", _node_judge)
    graph.add_node("generate", _node_generate)
    graph.add_node("save", _make_save_node(db))
    graph.set_entry_point("search")
    graph.add_edge("search", "judge")
    graph.add_edge("judge", "generate")
    graph.add_edge("generate", "save")
    graph.add_edge("save", END)
    return graph.compile()


@router.post("/chat/ask")
@user_limiter.limit(USER_RATE_LIMIT)
@ip_limiter.limit(IP_RATE_LIMIT)
def ask(
    request: Request,
    payload: AskRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_self(current_user, payload.newcomer_id)

    # "조회" 단계 — Assignment 확인은 그래프 진입 전에 수행 (없으면 검색/생성/저장을
    # 아예 안 타야 하므로 그래프 노드가 아니라 사전 체크로 둠, guidelines 3-3).
    document_id = _get_assignment_document_id(db, payload.newcomer_id)
    if document_id is None:
        raise HTTPException(status_code=404, detail="배정된 문서가 없습니다")

    graph = _build_graph(db)
    result = graph.invoke(
        {
            "newcomer_id": payload.newcomer_id,
            "question": payload.question,
            "document_id": document_id,
            "search_results": [],
            "answered": False,
            "answer": "",
            "matched_chapter_id": None,
            "question_type": "fact",
        }
    )

    return {
        "answer": result["answer"],
        "source_chapter_id": result["matched_chapter_id"],
        "answered": result["answered"],
    }


@router.get("/chat/logs")
def get_logs(
    newcomer_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 본인(신입) 또는 mentor만 조회 가능 — mentor가 실제 담당자인지까지는 아래 TODO 참고.
    if current_user["role"] == "newcomer":
        require_self(current_user, newcomer_id)
    else:
        # TODO(연동 필요 — 팀원 B): 이 mentor가 실제로 이 newcomer_id를 담당하는지
        # Assignment로 검증해야 함(3-9 문서 조회 권한과 같은 취지). 지금은 role=mentor면
        # 통과 — 병합 후 반드시 보강 필요.
        pass

    rows = (
        db.query(ChatLogORM)
        .filter_by(newcomer_id=newcomer_id)
        .order_by(ChatLogORM.created_at.desc())
        .all()
    )
    return [
        ChatLog(
            log_id=row.log_id,
            newcomer_id=row.newcomer_id,
            question=row.question,
            answered=row.answered,
            matched_chapter_id=row.matched_chapter_id,
            question_type=row.question_type,
            created_at=row.created_at,
        )
        for row in rows
    ]
