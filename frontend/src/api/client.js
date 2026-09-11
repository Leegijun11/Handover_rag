import axios from "axios";

// 공통 axios 인스턴스 (guidelines 5-2). baseURL은 배포 시 Railway 백엔드 URL로 교체.
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
});

export const TOKEN_STORAGE_KEY = "access_token";
export const USER_STORAGE_KEY = "current_user";

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
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  const visitorId = getOrCreateVisitorId();
  if (visitorId) {
    config.headers["X-Visitor-Id"] = visitorId;
  }
  return config;
});

/**
 * 서버 에러 바디에서 사람이 읽을 메시지를 뽑아낸다.
 *
 * 백엔드는 main.py의 전역 예외 핸들러로 모든 에러를 3-7번 공통 포맷
 * ({error: true, message: "..."})으로 통일해서 내려준다. 아래 나머지 분기는
 * 그 핸들러를 거치지 않는 경로(프록시/게이트웨이가 대신 만든 응답, 아직 갱신 안 된
 * 배포본 등)를 대비한 폴백이다 — 화면 코드가 이 분기를 매번 하지 않도록 여기서 흡수한다.
 */
function extractErrorMessage(error) {
  const data = error.response?.data;
  if (!data) {
    // 응답 자체가 없는 경우. 서버가 꺼져 있을 때뿐 아니라, 서버가 500을 보냈는데
    // 브라우저가 CORS로 막았을 때도 여기로 온다 — main.py의 미처리 예외 핸들러는
    // CORSMiddleware 바깥(ServerErrorMiddleware)에서 응답을 만들어서 500 응답에만
    // Access-Control-Allow-Origin이 붙지 않는다. 둘을 구분할 방법이 없으므로
    // 양쪽을 포괄하는 문구를 쓴다. (근본 해결은 조장님 main.py 쪽)
    return "서버에 연결할 수 없거나 서버에서 오류가 발생했습니다";
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

// 로그인/회원가입 요청 자체. 여기서 나오는 401은 "자격이 틀렸다"는 뜻이지
// "세션이 만료됐다"가 아니므로, 아래 만료 처리를 태우면 안 된다.
const AUTH_ENDPOINTS = ["/user/login", "/user/register"];

function isAuthAttempt(config) {
  const url = config?.url || "";
  return AUTH_ENDPOINTS.some((path) => url.endsWith(path));
}

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;

    // 토큰 만료(JWT_EXPIRE_MINUTES=1440, 24시간) 또는 위조 시 401.
    // 저장된 토큰을 지우고 로그인 화면으로 보낸다 — 이 처리가 없으면
    // 하루 뒤 재접속한 사용자는 모든 요청이 조용히 실패하는 화면에 갇힌다.
    //
    // 로그인 시도 실패는 제외한다. 데모 화면에서 자격이 틀렸을 때 화면이 통째로
    // /login으로 넘어가버려서, 왜 안 됐는지 알려주는 안내가 보이지도 않았다.
    // (로그인 화면 자신은 pathname 검사에 걸려 우연히 멀쩡했을 뿐이다.)
    if (status === 401 && !isAuthAttempt(error.config)) {
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
