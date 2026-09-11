import apiClient from "../../api/client";

// backend/routers/document.py와 1:1 대응 (guidelines 3-2 — file 업로드 / chapters 직접 입력)
//
// 두 입력 방식 모두 multipart/form-data로 보낸다. 3-2 표기상 "직접 입력"은 JSON 배열이지만,
// FastAPI는 한 엔드포인트에서 multipart와 application/json을 파라미터 선언만으로 동시에
// 받을 수 없어서, 팀원 A가 chapters도 Form 필드(JSON 문자열)로 받도록 구현했다.
// (mentor_id: Form(...), file: File(None), chapters: Form(None) — 팀원 A와 협의 완료)
//
// Content-Type은 직접 지정하지 않는다 — FormData를 넘기면 axios가 헤더를 브라우저에
// 맡겨서 multipart 경계(boundary) 문자열이 자동으로 붙는다. 직접 "multipart/form-data"로
// 박으면 boundary가 빠져 서버가 파싱하지 못한다.
function buildUploadForm(mentorId) {
  const formData = new FormData();
  formData.append("mentor_id", mentorId);
  return formData;
}

export function uploadDocumentFile(mentorId, file) {
  const formData = buildUploadForm(mentorId);
  formData.append("file", file);
  return apiClient.post("/document/upload", formData);
}

export function uploadDocumentChapters(mentorId, chapters) {
  const formData = buildUploadForm(mentorId);
  // 서버가 Form 필드로 받은 뒤 json.loads로 파싱한다 (routers/document.py _parse_chapters_json).
  formData.append("chapters", JSON.stringify(chapters));
  return apiClient.post("/document/upload", formData);
}

export function getChapters(documentId) {
  return apiClient.get(`/document/${documentId}/chapters`);
}
