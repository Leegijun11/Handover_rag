import axios from "axios";

// 공통 axios 인스턴스 (guidelines 5-2). baseURL은 배포 시 Railway 백엔드 URL로 교체.
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
});

export const TOKEN_STORAGE_KEY = "access_token";
export const USER_STORAGE_KEY = "current_user";

// 로그인 시 저장해둔 JWT를 모든 요청에 자동으로 실어 보냄 (guidelines 3-9).
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/**
 * 서버 에러 바디에서 사람이 읽을 메시지를 뽑아낸다.
 *
 * guidelines 3-7은 모든 에러를 {error: true, message: "..."} 로 통일하기로 했지만,
 * 현재 백엔드는 상황에 따라 세 가지 형태로 응답한다 (조장에게 통일 요청해둔 상태):
 *   - HTTPException        -> {detail: "..."}
 *   - 요청 검증 실패(422)  -> {detail: [{msg: "...", ...}]}
 *   - rate limit(429)      -> {error: "Rate limit exceeded: ..."}
 * 화면 코드가 이 분기를 매번 하지 않도록 여기서 한 번만 흡수한다.
 * 백엔드가 공통 포맷으로 통일되면 이 함수는 message 한 줄만 남기고 정리할 수 있다.
 */
function extractErrorMessage(error) {
  const data = error.response?.data;
  if (!data) {
    return error.message || "네트워크 오류가 발생했습니다";
  }
  if (typeof data.message === "string") {
    return data.message;
  }
  if (typeof data.detail === "string") {
    return data.detail;
  }
  if (Array.isArray(data.detail) && data.detail.length > 0) {
    return data.detail[0]?.msg || "요청 형식이 올바르지 않습니다";
  }
  if (typeof data.error === "string") {
    return data.error;
  }
  return error.message || "알 수 없는 오류가 발생했습니다";
}

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;

    // 토큰 만료(JWT_EXPIRE_MINUTES=1440, 24시간) 또는 위조 시 401.
    // 저장된 토큰을 지우고 로그인 화면으로 보낸다 — 이 처리가 없으면
    // 하루 뒤 재접속한 사용자는 모든 요청이 조용히 실패하는 화면에 갇힌다.
    if (status === 401) {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      localStorage.removeItem(USER_STORAGE_KEY);
      if (!window.location.pathname.startsWith("/login")) {
        window.location.replace("/login");
      }
    }

    // 화면에서는 err.userMessage 하나만 보고 알림을 띄우면 된다.
    error.userMessage = extractErrorMessage(error);
    return Promise.reject(error);
  }
);

export default apiClient;
