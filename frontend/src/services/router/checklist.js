import apiClient from "../../api/client";

// backend/routers/checklist.py, checklist_draft.py와 1:1 대응
export function saveChecklist(items) {
  return apiClient.post("/checklist", { items });
}

export function getChecklist(newcomerId) {
  return apiClient.get("/checklist", { params: { newcomer_id: newcomerId } });
}

export function updateChecklistItem(itemId, payload) {
  return apiClient.patch(`/checklist/${itemId}`, payload);
}

export function reorderChecklistItem(itemId, order) {
  return apiClient.patch(`/checklist/${itemId}/reorder`, { order });
}

export function completeChecklistItem(itemId, newcomerId) {
  return apiClient.post(`/checklist/${itemId}/complete`, { newcomer_id: newcomerId });
}

// 아래 둘은 3-5번 표에 없는 엔드포인트다. 팀원 A가 구현해서 브랜치에 올렸고
// (사수가 잘못 넣은 항목을 지울 방법이 없고, 신입이 완료를 되돌릴 방법도 없어서),
// 화면에서 쓰고 있다. 3번 문서 반영은 조장님 확인이 필요하다.
export function deleteChecklistItem(itemId) {
  return apiClient.delete(`/checklist/${itemId}`);
}

export function uncompleteChecklistItem(itemId, newcomerId) {
  return apiClient.post(`/checklist/${itemId}/uncomplete`, { newcomer_id: newcomerId });
}

export function draftChecklist(documentId) {
  return apiClient.post("/checklist/draft", { document_id: documentId });
}
