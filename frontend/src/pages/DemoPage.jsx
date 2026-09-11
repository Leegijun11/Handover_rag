import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../services/router/user";
import { homePathFor, saveSession } from "../api/session";
import Button from "../components/common/Button";

/**
 * 데모 계정 자격 (guidelines 1-8, 6-6).
 *
 * 새 API 없이 POST /user/login을 그대로 재사용한다. 실제 사용자 계정이 아니라
 * 공개해도 무방한 값이라 프론트에 하드코딩한다.
 *
 * 주의: backend/scripts/seed_demo.py(조장 조율)가 만드는 계정과 이메일·비밀번호가
 * 정확히 같아야 한다. user_id도 고정값(demo-mentor-a/-b/-c, demo-newcomer-a/-b/-c)으로
 * 시딩되어야 .env의 DEMO_USER_IDS(rate limit 예외)와 맞는다.
 */
const DEMO_PASSWORD = "demo-handover-2026";

const COMPANIES = [
  {
    id: "a",
    name: "새싹커머스",
    field: "이커머스 · 상품 운영",
    summary:
      "상품 등록과 정산 절차가 담긴 인수인계서. 체크리스트 5개, 질문 로그 12건이 쌓여 있습니다.",
    mentorEmail: "demo-mentor-a@handover.demo",
    newcomerEmail: "demo-newcomer-a@handover.demo",
  },
  {
    id: "b",
    name: "한빛물류",
    field: "물류 · 배송 관제",
    summary:
      "배차와 사고 대응 매뉴얼. 완료 체크는 했지만 같은 업무를 계속 묻는 신입의 리포트가 준비돼 있습니다.",
    mentorEmail: "demo-mentor-b@handover.demo",
    newcomerEmail: "demo-newcomer-b@handover.demo",
  },
  {
    id: "c",
    name: "미래테크",
    field: "SI · 백엔드 개발",
    summary:
      "배포 절차와 온콜 대응. 질문이 후반부에 끊긴 침묵 위험 사례를 볼 수 있습니다.",
    mentorEmail: "demo-mentor-c@handover.demo",
    newcomerEmail: "demo-newcomer-c@handover.demo",
  },
];

function DemoPage() {
  const navigate = useNavigate();
  // 어느 버튼을 눌렀는지까지 기억해서 그 버튼만 "접속 중"으로 바꾼다.
  const [pending, setPending] = useState(null);
  const [error, setError] = useState("");

  async function enterAs(company, role) {
    const email = role === "mentor" ? company.mentorEmail : company.newcomerEmail;
    setPending(`${company.id}-${role}`);
    setError("");
    try {
      const { data } = await login({ email, password: DEMO_PASSWORD });
      saveSession(data.access_token, data.user);
      navigate(homePathFor(data.user), { replace: true });
    } catch (err) {
      // 시딩 전이면 401이 온다 — 심사위원이 보게 될 화면이므로 원인을 알 수 있게 적는다.
      setError(
        err.userMessage
          ? `${company.name} 데모 계정으로 들어갈 수 없습니다 (${err.userMessage})`
          : "데모 계정에 접속할 수 없습니다",
      );
      setPending(null);
    }
  }

  return (
    <>
      <header className="app-header">
        <span className="brand">
          HAND<span>OVER</span>
        </span>
        <div className="spacer" />
        <Button size="sm" onClick={() => navigate("/login")}>
          로그인 화면으로
        </Button>
      </header>

      <main className="app-main">
        <h3 className="page-title">회사를 선택하세요</h3>
        <p className="page-desc">
          가입 없이 미리 채워둔 데이터로 전체 흐름을 체험할 수 있습니다. 사수와 신입 두 시점 모두
          볼 수 있습니다.
        </p>

        {error && <div className="banner banner-error">{error}</div>}

        <div className="demo-grid">
          {COMPANIES.map((company) => (
            <div className="card demo-card" key={company.id}>
              <h4>{company.name}</h4>
              <div className="demo-field">{company.field}</div>
              <p>{company.summary}</p>
              <div className="actions">
                <Button
                  variant="primary"
                  disabled={pending !== null}
                  onClick={() => enterAs(company, "newcomer")}
                >
                  {pending === `${company.id}-newcomer` ? "접속 중…" : "신입으로 체험"}
                </Button>
                <Button
                  disabled={pending !== null}
                  onClick={() => enterAs(company, "mentor")}
                >
                  {pending === `${company.id}-mentor` ? "접속 중…" : "사수로 체험"}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </main>
    </>
  );
}

export default DemoPage;
