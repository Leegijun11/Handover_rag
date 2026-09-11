"""챗봇 RAG (담당: 조장) — guidelines 3-3, 3-9, 4-1, 5-9.

핵심 흐름 (LangGraph 그래프):
  1. 조회: newcomer_id로 Assignment 조회 -> document_id 확정 (Assignment 없으면 404)
  2. 검색: document_id 범위로 ChromaDB 검색
  3. 판단+생성: 검색된 발췌로 실제 답변이 가능한지까지 LLM이 한 번에 판단해서 생성
     (부족하면 answered=False + 고정 문구 — "문서 보강" 언급 절대 금지, guidelines 1-7, 4-1)
  4. 저장: ChatLog 생성 (question_type 분류 포함)

"판단"이 거리(distance) 임계값이 아니라 LLM 판단인 이유: ChromaDB 기본 거리 지표가
코사인이 아니라 L2라 절대값 스케일을 맞추기 까다롭고, 실측해보니 정답 청크의 거리가
무관한 질문의 거리보다 더 크게 나오는 경우도 있어 숫자 하나로 자르는 게 신뢰할 수
없었다(실제 재현: "CS 응대 기준" 질문 — 정답 청크 distance=1.46, "연차 신청" 같은
무관한 질문 distance=1.42로 더 가까움). 검색된 텍스트를 실제로 읽고 판단하는 LLM
쪽이 훨씬 안정적이라 그쪽으로 옮김 — 대신 매 질문마다 LLM 호출이 확정으로 발생함
(이전엔 거리 게이트에서 걸러지면 호출 자체를 스킵했음, 5-9 비용에 참고).
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
from models.assignment import get_assignment_by_newcomer
from schemas.chat import ChatLog

router = APIRouter(tags=["chat"])

NO_ANSWER_MESSAGE = "문서에 없는 내용이니 담당자에게 문의하세요."
# LLM에게 "발췌에 답이 없다"는 걸 신호하게 하는 sentinel. 이 문자열이 그대로(다른 말
# 없이) 나오면 answered=False로 처리 — system prompt에서 정확히 이 값만 출력하도록 지시.
NOT_FOUND_SENTINEL = "NOT_FOUND_IN_DOCUMENT"


class AskRequest(BaseModel):
    newcomer_id: str
    question: str


def _get_assignment_document_id(db: Session, newcomer_id: str) -> str | None:
    row = get_assignment_by_newcomer(db, newcomer_id)
    return row.document_id if row else None


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


def _node_generate(state: ChatState) -> ChatState:
    hits = state["search_results"]
    context = "\n\n".join(h["text"] for h in hits) if hits else ""
    raw_answer = chat_complete(
        system_prompt=(
            "너는 신입사원 온보딩을 돕는 사내 챗봇이다. 아래 인수인계서 발췌 내용만 근거로 "
            "간결하고 정확하게 답변하라. 발췌 내용에 질문에 대한 답이 실제로 없으면, "
            f'다른 말 없이 정확히 "{NOT_FOUND_SENTINEL}" 라고만 답하라. 추측하거나 지어내지 마라.'
        ),
        user_prompt=f"[인수인계서 발췌]\n{context}\n\n[질문]\n{state['question']}",
    )

    if NOT_FOUND_SENTINEL in raw_answer:
        state["answered"] = False
        state["answer"] = NO_ANSWER_MESSAGE
        # TODO(연동 필요 — 팀원 A): 4-1 요구사항은 "실패 시 챕터 제목 목록 중 LLM이
        # 근접 추정"을 요구하지만, 챕터 제목 목록을 얻으려면 DocumentChapter 조회가
        # 필요함. 지금은 "추정도 어려우면 None" 폴백으로 처리.
        state["matched_chapter_id"] = None
    else:
        state["answered"] = True
        state["answer"] = raw_answer
        state["matched_chapter_id"] = hits[0]["chapter_id"] if hits else None

    state["question_type"] = _classify_question_type(state["question"])
    return state


def _make_save_node(db: Session):
    def _node_save(state: ChatState) -> ChatState:
        db.add(
            ChatLogORM(
                log_id=str(uuid.uuid4()),
                newcomer_id=state["newcomer_id"],
                document_id=state["document_id"],
                question=state["question"],
                answer=state["answer"],
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
    graph.add_node("generate", _node_generate)
    graph.add_node("save", _make_save_node(db))
    graph.set_entry_point("search")
    graph.add_edge("search", "generate")
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
            document_id=row.document_id,
            question=row.question,
            answer=row.answer,
            answered=row.answered,
            matched_chapter_id=row.matched_chapter_id,
            question_type=row.question_type,
            created_at=row.created_at,
        )
        for row in rows
    ]
