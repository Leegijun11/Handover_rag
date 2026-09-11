/**
 * 이 브라우저에서 업로드한 인수인계서 목록 (사수별).
 *
 * 왜 필요한가: 3번 문서에 "사수가 올린 문서 목록"을 주는 API가 없다. document_id는
 * POST /document/upload 응답에서 딱 한 번 나오고 그다음엔 어디서도 다시 받을 수 없어서,
 * 배정 화면에서 문서를 고르게 하려면 그 순간 받은 값을 프론트가 들고 있어야 한다.
 *
 * 한계는 분명하다 — 브라우저를 바꾸거나 저장소를 비우면 목록이 사라지고, 시딩된
 * 데모 계정처럼 이 브라우저에서 올린 적 없는 문서는 나오지 않는다. 그래서 배정
 * 화면은 document_id 직접 입력 경로를 함께 둔다. 목록 API가 생기면 이 파일은 지운다.
 */

const KEY_PREFIX = "uploaded_documents:";
const MAX_ITEMS = 20;

function keyFor(mentorId) {
  return `${KEY_PREFIX}${mentorId}`;
}

export function listUploadedDocuments(mentorId) {
  if (!mentorId) return [];
  try {
    const raw = localStorage.getItem(keyFor(mentorId));
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function rememberUploadedDocument(mentorId, { documentId, chapterTitles }) {
  if (!mentorId || !documentId) return;
  // 문서에 이름 필드가 없어서(2번 문서 DocumentChapter만 존재) 첫 업무 제목을 라벨로 쓴다.
  const label = chapterTitles?.[0] || "제목 없는 인수인계서";
  const entry = {
    documentId,
    label,
    chapterCount: chapterTitles?.length ?? 0,
    uploadedAt: new Date().toISOString(),
  };
  try {
    const next = [entry, ...listUploadedDocuments(mentorId).filter((d) => d.documentId !== documentId)];
    localStorage.setItem(keyFor(mentorId), JSON.stringify(next.slice(0, MAX_ITEMS)));
  } catch {
    // 저장 실패는 무시한다 — 배정 화면의 직접 입력 경로로 여전히 배정할 수 있다.
  }
}
