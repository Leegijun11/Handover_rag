import { NavLink, useNavigate } from "react-router-dom";
import { clearSession, getCurrentUser } from "../../api/session";
import Button from "./Button";

// 역할별 메뉴 (guidelines 1-2). 신입 화면에 리포트는 넣지 않는다 — HR 전용.
const NAV = {
  mentor: [
    { to: "/hr/upload", label: "인수인계서 업로드" },
    { to: "/hr/assign", label: "신입 배정" },
    { to: "/hr/checklist", label: "체크리스트 관리" },
    { to: "/hr/report", label: "적응도 리포트" },
  ],
  newcomer: [
    { to: "/chat", label: "챗봇에게 물어보기" },
    { to: "/checklist", label: "체크리스트" },
  ],
};

/**
 * 로그인 이후 모든 화면의 공통 틀 — 헤더 + 좌측 메뉴 + 본문.
 *
 * mentorName은 신입 화면에서만 쓴다. 신입이 자기 사수 이름을 보려면
 * GET /assignment?newcomer_id= 로 mentor_id를 받고 GET /user/{mentor_id}를
 * 한 번 더 불러야 해서(통합 API 없음, guidelines 4-3), 그 조회를 하는 페이지가
 * 결과를 내려주는 형태로 둔다.
 */
function AppShell({ mentorName, children }) {
  const navigate = useNavigate();
  const user = getCurrentUser();
  const menu = NAV[user?.role] || [];

  function handleLogout() {
    // 서버에 토큰 무효화가 없어서 로컬 저장소를 비우는 것까지가 로그아웃이다.
    clearSession();
    navigate("/login", { replace: true });
  }

  return (
    <>
      <header className="app-header">
        <span className="brand">
          HAND<span>OVER</span>
        </span>
        <div className="spacer" />
        <span className="who">
          <b>{user?.name}</b> 님
          {user?.role === "mentor" ? " · 사수" : mentorName ? ` · 사수 ${mentorName}` : ""}
        </span>
        <Button size="sm" onClick={handleLogout}>
          로그아웃
        </Button>
      </header>

      <div className="app-body">
        <nav className="app-nav">
          {menu.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <main className="app-main">{children}</main>
      </div>
    </>
  );
}

export default AppShell;
