import axios from "axios";

// 공통 axios 인스턴스 (guidelines 5-2). baseURL은 배포 시 Railway 백엔드 URL로 교체.
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
});

// 로그인 시 저장해둔 JWT를 모든 요청에 자동으로 실어 보냄 (guidelines 3-9).
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default apiClient;
