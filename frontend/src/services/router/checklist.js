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

export function draftChecklist(documentId) {
  return apiClient.post("/checklist/draft", { document_id: documentId });
}
