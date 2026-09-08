import axios from "axios";

// 공통 axios 인스턴스 (guidelines 5-2). baseURL은 배포 시 Railway 백엔드 URL로 교체.
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
});

// 방문자별 고유 ID. 데모 계정(1-8)을 여러 명이 동시에 같은 로그인으로 쓸 때,
// 같은 WiFi 등으로 IP가 겹쳐도 브라우저별로 rate limit이 분리되게 하기 위함
// (guidelines 5-9 항목 6, core/rate_limit.py가 X-Visitor-Id 헤더를 우선 사용).
// 일반 회원가입 사용자에게는 아무 영향 없음 — 서버가 데모 계정에만 이 값을 씀.
function getOrCreateVisitorId() {
  try {
    let id = localStorage.getItem("visitor_id");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("visitor_id", id);
    }
    return id;
  } catch {
    return null; // localStorage 접근 불가(프라이빗 모드 등) 시 헤더 생략, IP로 폴백
  }
}

// 로그인 시 저장해둔 JWT를 모든 요청에 자동으로 실어 보냄 (guidelines 3-9).
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  const visitorId = getOrCreateVisitorId();
  if (visitorId) {
    config.headers["X-Visitor-Id"] = visitorId;
  }
  return config;
});

export default apiClient;
