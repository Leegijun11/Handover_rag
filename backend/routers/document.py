"""문서 처리 (담당: 팀원 A) — guidelines 3-2, 3-9, 4-2.

TODO(팀원 A): 아래는 main.py가 부팅되도록 만든 최소 스텁입니다. 직접 채워서 구현하세요.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from core.auth import CurrentUser, get_current_user

router = APIRouter(tags=["document"])


@router.post("/document/upload", status_code=201)
def upload_document(
    file: UploadFile | None = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    # TODO(팀원 A): require_role(current_user, "mentor") 먼저 검증
    # - file이 오면: 목차(장-절) 자동 파싱 -> DocumentChapter 생성
    # - chapters(list[{title, content}])가 오면: 파싱 없이 그대로 DocumentChapter 생성
    # - 두 경로 모두 챕터별 청킹 -> DocumentChunk 생성 -> 임베딩 -> ChromaDB 저장
    #   (core.chroma_client.get_collection(document_id) 사용, 청크 크기 기준은 재량)
    # - 이 document_id를 이 mentor(current_user["user_id"])가 올렸다는 매핑을 내부에
    #   기록해둘 것 — get_chapters의 권한 검증(아래)에 필요. 2번 문서엔 없는 필드라
    #   내 재량으로 별도 테이블/컬럼에 저장 (guidelines 3-9)
    raise HTTPException(status_code=501, detail="담당자(팀원 A) 구현 필요")


@router.get("/document/{document_id}/chapters")
def get_chapters(document_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(팀원 A): 로그인 여부만으로는 부족함 — 챕터 본문 전체가 노출되는 조회라
    # 토큰의 user_id가 (a) 이 document_id를 업로드한 mentor이거나,
    # (b) 이 document_id로 배정된 newcomer(Assignment.newcomer_id)인지 확인해야 함.
    # 아니면 403. (b) 확인에 Assignment 조회 필요 — 팀원 B와 조회 방식 협의 (guidelines 3-9)
    raise HTTPException(status_code=501, detail="담당자(팀원 A) 구현 필요")
