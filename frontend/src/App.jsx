import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { getCurrentUser, getToken, homePathFor } from "./api/session";
import AppShell from "./components/common/AppShell";
import NewcomerScope from "./components/common/NewcomerScope";
import RequireAuth from "./components/common/RequireAuth";

import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DemoPage from "./pages/DemoPage";
import UploadPage from "./pages/hr/UploadPage";
import AssignPage from "./pages/hr/AssignPage";
import ChecklistManagePage from "./pages/hr/ChecklistManagePage";
import ReportPage from "./pages/hr/ReportPage";
import ChatPage from "./pages/newcomer/ChatPage";
import ChecklistPage from "./pages/newcomer/ChecklistPage";

/** 로그인한 화면은 전부 같은 셸 안에 들어간다. */
function Shell({ role, children }) {
  return (
    <RequireAuth role={role}>
      <AppShell>{children}</AppShell>
    </RequireAuth>
  );
}

/**
 * 신입 화면 전용 셸 — 셸 바깥에 NewcomerScope를 한 겹 더 씌운다.
 * 배정 정보를 여기서 한 번만 받아 헤더(사수 이름)와 두 화면이 나눠 쓴다.
 */
function NewcomerShell({ children }) {
  return (
    <RequireAuth role="newcomer">
      <NewcomerScope>
        <AppShell>{children}</AppShell>
      </NewcomerScope>
    </RequireAuth>
  );
}

/** "/" 진입 — 로그인 상태면 역할별 첫 화면으로, 아니면 로그인으로. */
function Landing() {
  const user = getCurrentUser();
  return <Navigate to={getToken() && user ? homePathFor(user) : "/login"} replace />;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />

        {/* 인증 불필요 (guidelines 3-9) */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/demo" element={<DemoPage />} />

        {/* 사수 전용 */}
        <Route path="/hr/upload" element={<Shell role="mentor"><UploadPage /></Shell>} />
        <Route path="/hr/assign" element={<Shell role="mentor"><AssignPage /></Shell>} />
        <Route path="/hr/checklist" element={<Shell role="mentor"><ChecklistManagePage /></Shell>} />
        {/* 리포트는 사수 전용 — 신입 화면에 노출하지 않는다 (guidelines 1-2) */}
        <Route path="/hr/report" element={<Shell role="mentor"><ReportPage /></Shell>} />

        {/* 신입 전용 */}
        <Route path="/chat" element={<NewcomerShell><ChatPage /></NewcomerShell>} />
        <Route path="/checklist" element={<NewcomerShell><ChecklistPage /></NewcomerShell>} />

        <Route path="*" element={<Landing />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
