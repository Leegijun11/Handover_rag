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

// 경로 변수가 newcomer_id가 아니라 report_id다 — 한 신입에게 리포트가 여러 건이라 하나를 지목한다.
export function deleteReport(reportId) {
  return apiClient.delete(`/report/${reportId}`);
}
