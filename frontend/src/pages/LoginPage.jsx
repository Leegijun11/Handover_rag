import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login } from "../services/router/user";
import { homePathFor, saveSession } from "../api/session";
import Button from "../components/common/Button";
import Field from "../components/common/Field";

function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const { data } = await login({ email, password });
      saveSession(data.access_token, data.user);
      navigate(homePathFor(data.user), { replace: true });
    } catch (err) {
      // 서버는 "이메일 없음"과 "비밀번호 틀림"을 같은 401/같은 문구로 준다.
      // 어느 쪽인지 안내하지 않는 것이 의도된 동작이므로 그대로 보여준다.
      setError(err.userMessage || "로그인에 실패했습니다");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <span className="wordmark">
          HAND<span>OVER</span>
        </span>
        <p className="tagline">인수인계 업무보조 챗봇</p>
        <p className="auth-sub" style={{ marginTop: 18 }}>
          넘기는 사람도, 받는 사람도 편한 인수인계
        </p>

        <form className="card" onSubmit={handleSubmit}>
          <Field label="이메일">
            {(props) => (
              <input
                {...props}
                type="email"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            )}
          </Field>

          <Field label="비밀번호" error={error}>
            {(props) => (
              <input
                {...props}
                type="password"
                placeholder="비밀번호를 입력하세요"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            )}
          </Field>

          <Button type="submit" variant="primary" block disabled={submitting}>
            {submitting ? "로그인 중…" : "로그인"}
          </Button>

          <div className="divider">또는</div>
          <Button block onClick={() => navigate("/demo")}>
            데모로 체험하기
          </Button>

          <div className="auth-links">
            <span>계정이 없으신가요?</span>
            <Link to="/register">회원가입</Link>
          </div>
        </form>
      </div>
    </div>
  );
}

export default LoginPage;
