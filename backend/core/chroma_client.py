import os

import chromadb

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")

_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)


def get_chroma_client() -> chromadb.PersistentClient:
    return _client


def get_collection(document_id: str):
    """컬렉션명 = document_id (guidelines 5-4) — 문서 단위로 검색 범위가 자연히 분리됨."""
    return _client.get_or_create_collection(name=document_id)
