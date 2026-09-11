import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { clearSession, getCurrentUser, homePathFor } from "../../api/session";
import { deleteUser } from "../../services/router/user";
import Button from "./Button";
import { useNewcomerScope } from "./NewcomerScope";

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
 * 사수 이름은 신입 화면에서만 뜬다. 조회에 두 번의 요청이 필요해서(통합 API 없음,
 * guidelines 4-3) 화면마다 따로 부르지 않고 NewcomerScope가 한 번 받아둔 값을 쓴다.
 * 사수 화면에는 그 Provider가 없어서 기본값(빈 문자열)이 들어오고, 이름 칸은 비워진다.
 */
function AppShell({ children }) {
  const navigate = useNavigate();
  const user = getCurrentUser();
  const menu = NAV[user?.role] || [];
  const { mentorName } = useNewcomerScope();
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  function handleLogout() {
    // 서버에 토큰 무효화가 없어서 로컬 저장소를 비우는 것까지가 로그아웃이다.
    clearSession();
    navigate("/login", { replace: true });
  }

  async function handleDeleteAccount() {
    if (!window.confirm("정말 탈퇴하시겠습니까? 이 작업은 되돌릴 수 없습니다.")) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteUser(user.user_id);
      clearSession();
      navigate("/login", { replace: true });
    } catch (err) {
      setDeleteError(err.userMessage || "탈퇴에 실패했습니다");
      setDeleting(false);
    }
  }

  return (
    <>
      <header className="app-header">
        <button
          type="button"
          className="brand brand-link"
          onClick={() => navigate(homePathFor(user))}
        >
          HAND<span>OVER</span>
        </button>
        <div className="spacer" />
        <span className="who">
          <b>{user?.name}</b> 님
          {user?.role === "mentor" ? " · 사수" : mentorName ? ` · 사수 ${mentorName}` : ""}
        </span>
        {deleteError && (
          <span className="hint" style={{ color: "var(--danger)" }}>
            {deleteError}
          </span>
        )}
        <Button size="sm" variant="danger" disabled={deleting} onClick={handleDeleteAccount}>
          {deleting ? "탈퇴 중…" : "회원탈퇴"}
        </Button>
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
