import apiClient from "../../api/client";

// backend/routers/document.py와 1:1 대응 (guidelines 3-2 — file 업로드 / chapters 직접 입력)
export function uploadDocumentFile(mentorId, file) {
  const formData = new FormData();
  formData.append("mentor_id", mentorId);
  formData.append("file", file);
  return apiClient.post("/document/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
}

export function uploadDocumentChapters(mentorId, chapters) {
  return apiClient.post("/document/upload", { mentor_id: mentorId, chapters });
}

export function getChapters(documentId) {
  return apiClient.get(`/document/${documentId}/chapters`);
}
