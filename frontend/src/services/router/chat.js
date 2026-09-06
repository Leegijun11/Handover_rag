import apiClient from "../../api/client";

// backend/routers/chat.py와 1:1 대응
export function askChat(newcomerId, question) {
  return apiClient.post("/chat/ask", { newcomer_id: newcomerId, question });
}

export function getChatLogs(newcomerId) {
  return apiClient.get("/chat/logs", { params: { newcomer_id: newcomerId } });
}
