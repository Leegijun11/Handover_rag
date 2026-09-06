from pydantic import BaseModel


class DocumentChapter(BaseModel):
    chapter_id: str  # 문서 내에서 고유 (예: "1-1")
    document_id: str
    title: str
    parent_id: str | None
    content: str


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str  # ChromaDB 검색 시 배정 문서로 필터링하는 데 사용
    chapter_id: str  # DocumentChapter.chapter_id 참조
    text: str
    embedding: list[float]
