import { TOKEN_STORAGE_KEY, USER_STORAGE_KEY } from "./client";

/**
 * 로그인 상태 보관 (guidelines 4-3 — 같은 브라우저로 재접속 시 재로그인 없이 이어서 사용).
 *
 * client.js와 같은 폴더에 두는 이유: 여기서 읽고 쓰는 두 키를 client.js가 정의하고,
 * 401 응답에서 지우는 것도 client.js다. 키를 만지는 코드를 한곳에 모아둔다.
 *
 * 서버에 로그아웃(토큰 무효화)은 없다 — 발급된 토큰은 만료(JWT_EXPIRE_MINUTES,
 * 기본 24시간)까지 유효하고, 로그아웃은 이 저장소를 비우는 것까지다. refresh token과
 * 함께 1차 범위 밖 (guidelines 6-5).
 */

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null; // 프라이빗 모드 등 localStorage 접근 불가
  }
}

export function getCurrentUser() {
  try {
    const raw = localStorage.getItem(USER_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    // 접근 불가이거나 저장된 값이 깨진 경우 — 비로그인으로 취급한다.
    return null;
  }
}

export function saveSession(accessToken, user) {
  try {
    localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  } catch {
    // 저장에 실패해도 이번 세션은 메모리 상태로 동작하게 두고 막지 않는다.
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(USER_STORAGE_KEY);
  } catch {
    /* 무시 */
  }
}

/** 로그인 직후 역할별 첫 화면 (guidelines 1-2). */
export function homePathFor(user) {
  return user?.role === "mentor" ? "/hr/upload" : "/chat";
}
