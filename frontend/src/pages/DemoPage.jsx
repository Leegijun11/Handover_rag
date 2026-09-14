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
 * 주의: backend/scripts/seed_demo.py(팀원 B 전담)가 만드는 계정과
 * 이메일·비밀번호가 정확히 같아야 한다. user_id도 고정값(demo-mentor-a/-b/-c/-d,
 * demo-newcomer-a/-b/-c/-d)으로 시딩되어야 .env의 DEMO_USER_IDS(rate limit 예외)와 맞는다.
 * 각 회사의 사수 계정은 이 신입 1명 외에도 신입 1~2명을 추가로 담당하도록 시딩된다
 * (사수 화면에서 "여러 신입 담당" 구조가 보이게 하기 위함, guidelines 1-8/6-6) — 그
 * 추가 신입들은 여기서 직접 로그인하지 않으므로 고정 id가 필요 없다.
 *
 * files는 frontend/public/demo-files의 원본 인수인계서다. 심사위원이 내려받아 사수 화면에서
 * 직접 올려보고 AI 체크리스트 초안까지 확인할 수 있게 둔다. 첫 파일은 seed_demo.py가 실제로
 * 업로드하는 원본과 같다.
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
    files: [
      { href: "/demo-files/a-handover.md", download: "새싹커머스_상품운영팀_인수인계서.md", label: "인수인계서" },
      { href: "/demo-files/a-season-event.md", download: "새싹커머스_시즌행사_운영가이드.md", label: "시즌 행사 가이드" },
    ],
  },
  {
    id: "b",
    name: "한빛물류",
    field: "물류 · 배송 관제",
    summary:
      "배차와 사고 대응 매뉴얼. 완료 체크는 했지만 같은 업무를 계속 묻는 신입의 리포트가 준비돼 있습니다.",
    mentorEmail: "demo-mentor-b@handover.demo",
    newcomerEmail: "demo-newcomer-b@handover.demo",
    files: [
      { href: "/demo-files/b-handover.md", download: "한빛물류_배송관제팀_인수인계서.md", label: "인수인계서" },
      { href: "/demo-files/b-night-shift.md", download: "한빛물류_야간관제_근무매뉴얼.md", label: "야간 관제 매뉴얼" },
    ],
  },
  {
    id: "c",
    name: "미래테크",
    field: "SI · 백엔드 개발",
    summary:
      "배포 절차와 온콜 대응. 기간 후반부에 질문이 끊긴 신입의 리포트를 볼 수 있습니다.",
    mentorEmail: "demo-mentor-c@handover.demo",
    newcomerEmail: "demo-newcomer-c@handover.demo",
    files: [
      { href: "/demo-files/c-handover.md", download: "미래테크_플랫폼개발팀_인수인계서.md", label: "인수인계서" },
      { href: "/demo-files/c-code-review.md", download: "미래테크_코드리뷰_브랜치규칙.md", label: "코드 리뷰 규칙" },
    ],
  },
  {
    id: "d",
    name: "그린푸드",
    field: "인사 · 채용/노무",
    summary:
      "채용부터 급여·평가까지의 인사 업무 인수인계서. 질문이 단순 확인에서 절차·판단으로 점점 깊어지는 성장 곡선 사례를 볼 수 있습니다.",
    mentorEmail: "demo-mentor-d@handover.demo",
    newcomerEmail: "demo-newcomer-d@handover.demo",
    files: [
      { href: "/demo-files/d-handover.md", download: "그린푸드_인사팀_인수인계서.md", label: "인수인계서" },
      { href: "/demo-files/d-review-season.md", download: "그린푸드_평가시즌_운영가이드.md", label: "평가 시즌 가이드" },
    ],
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
              <div className="demo-files">
                <span>원본 파일</span>
                {company.files.map((file) => (
                  <a key={file.href} href={file.href} download={file.download}>
                    {file.label}
                  </a>
                ))}
              </div>
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
