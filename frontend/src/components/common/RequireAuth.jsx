import { Navigate, useLocation } from "react-router-dom";
import { getCurrentUser, getToken, homePathFor } from "../../api/session";

/**
 * 로그인/역할 확인 후 통과시키는 라우트 가드.
 *
 * 여기서 막는 건 화면 진입일 뿐이고 실제 권한은 서버가 판단한다 (guidelines 3-9).
 * 저장소의 값은 사용자가 고칠 수 있으므로, 이걸 통과했다고 API가 통과하는 건 아니다.
 * 목적은 "신입이 리포트 화면 URL을 직접 쳐서 빈 화면을 보는" 상황을 없애는 것이다.
 *
 * 토큰이 만료된 경우는 여기서 알 수 없다 — 첫 API 호출이 401을 받고 client.js의
 * 인터셉터가 저장소를 비운 뒤 /login으로 보낸다.
 */
function RequireAuth({ role, children }) {
  const location = useLocation();
  const user = getCurrentUser();

  if (!getToken() || !user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  // 역할이 다르면 로그인 화면이 아니라 자기 첫 화면으로 보낸다 — 이미 로그인한
  // 사람에게 다시 로그인하라고 하는 건 막다른 길이다.
  if (role && user.role !== role) {
    return <Navigate to={homePathFor(user)} replace />;
  }

  return children;
}

export default RequireAuth;
