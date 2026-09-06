import apiClient from "../../api/client";

// backend/routers/report.py와 1:1 대응
export function generateReport(newcomerId, periodStart, periodEnd) {
  return apiClient.post("/report/generate", {
    newcomer_id: newcomerId,
    period_start: periodStart,
    period_end: periodEnd,
  });
}

export function getLatestReport(newcomerId) {
  return apiClient.get(`/report/${newcomerId}`);
}

export function getReportHistory(newcomerId) {
  return apiClient.get(`/report/${newcomerId}/history`);
}
