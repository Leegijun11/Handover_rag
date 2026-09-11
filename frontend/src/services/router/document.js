import apiClient from "../../api/client";

// backend/routers/document.py와 1:1 대응 (guidelines 3-2 — file 업로드 / chapters 직접 입력)
//
// 두 입력 방식 모두 multipart/form-data로 보낸다. 3-2 표기상 "직접 입력"은 JSON 배열이지만,
// FastAPI는 한 엔드포인트에서 multipart와 application/json을 파라미터 선언만으로 동시에
// 받을 수 없어서, 팀원 A가 chapters도 Form 필드(JSON 문자열)로 받도록 구현했다.
// (mentor_id: Form(...), files: File(None) 복수, chapters: Form(None) — 팀원 A와 협의 완료)
//
// Content-Type은 직접 지정하지 않는다 — FormData를 넘기면 axios가 헤더를 브라우저에
// 맡겨서 multipart 경계(boundary) 문자열이 자동으로 붙는다. 직접 "multipart/form-data"로
// 박으면 boundary가 빠져 서버가 파싱하지 못한다.
// label은 목록 화면(배정 드롭다운)에 보여줄 제목. 비우면 서버가 기본 규칙으로
// 계산한다(파일 모드: 첫 파일명에서 확장자 제거, chapters 모드: 첫 챕터 제목) —
// routers/document.py upload_document 참고.
function buildUploadForm(mentorId, label) {
  const formData = new FormData();
  formData.append("mentor_id", mentorId);
  if (label && label.trim()) formData.append("label", label.trim());
  return formData;
}

export function uploadDocumentFiles(mentorId, files, label) {
  const formData = buildUploadForm(mentorId, label);
  // 같은 필드명("files")으로 여러 번 append하면 FastAPI가 list[UploadFile]로 받는다
  // (routers/document.py — 파일 여러 개로 나뉜 인수인계서 지원, guidelines 3-2 신설).
  files.forEach((file) => formData.append("files", file));
  return apiClient.post("/document/upload", formData);
}

export function uploadDocumentChapters(mentorId, chapters, label) {
  const formData = buildUploadForm(mentorId, label);
  // 서버가 Form 필드로 받은 뒤 json.loads로 파싱한다 (routers/document.py _parse_chapters_json).
  formData.append("chapters", JSON.stringify(chapters));
  return apiClient.post("/document/upload", formData);
}

export function getChapters(documentId) {
  return apiClient.get(`/document/${documentId}/chapters`);
}

// 이 사수가 올린 문서 목록, 최신순 (guidelines 3-2 신설). 예전엔 이 목록을 브라우저
// localStorage로만 들고 있어서(api/documentHistory.js, 삭제됨) 다른 브라우저/기기에서는
// 안 보였다 — 이제 DB 기반이라 어디서 로그인해도 같은 목록이 나온다.
export function listMyDocuments(mentorId) {
  return apiClient.get("/document", { params: { mentor_id: mentorId } });
}
