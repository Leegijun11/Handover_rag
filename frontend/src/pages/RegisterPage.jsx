import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login, register } from "../services/router/user";
import { homePathFor, saveSession } from "../api/session";
import Button from "../components/common/Button";
import Field from "../components/common/Field";

const MIN_PASSWORD_LENGTH = 8;
const HANGUL = /[ㄱ-ㅎㅏ-ㅣ가-힣]/;

/**
 * 아래 검사는 서버 규칙(routers/user.py)을 프론트에서 한 번 더 보는 것으로, 왕복을
 * 줄이려는 것이지 서버 검증을 대신하지 않는다. 다만 두 가지는 프론트에만 있는 규칙이다.
 *  - 비밀번호 확인: 서버로 보내지 않는다
 *  - 한글 금지: 서버는 아직 한글 비밀번호를 받는다 (bcrypt 72바이트 방어만 있음)
 */
function validate({ name, email, password, passwordConfirm }) {
  const errors = {};

  if (!name.trim()) errors.name = "이름을 입력하세요";

  const normalized = email.trim().toLowerCase();
  const [local, domain] = normalized.split("@");
  if (!normalized) errors.email = "이메일을 입력하세요";
  else if (!local || !domain || !domain.includes(".") || normalized.includes(" "))
    errors.email = "이메일 형식이 올바르지 않습니다";

  if (!password) errors.password = "비밀번호를 입력하세요";
  else if (HANGUL.test(password)) errors.password = "비밀번호에 한글은 사용할 수 없습니다";
  else if (password.length < MIN_PASSWORD_LENGTH)
    errors.password = `비밀번호는 ${MIN_PASSWORD_LENGTH}자 이상이어야 합니다`;

  if (!passwordConfirm) errors.passwordConfirm = "비밀번호를 한 번 더 입력하세요";
  else if (password !== passwordConfirm) errors.passwordConfirm = "비밀번호가 일치하지 않습니다";

  return errors;
}

function RegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    passwordConfirm: "",
    role: "newcomer",
  });
  // 입력을 시작하기도 전에 빨간 글씨가 뜨지 않도록, 한 번 벗어난 칸만 에러를 보여준다.
  const [touched, setTouched] = useState({});
  const [serverError, setServerError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const errors = validate(form);
  const isValid = Object.keys(errors).length === 0;

  function update(key) {
    return (e) => {
      setForm((prev) => ({ ...prev, [key]: e.target.value }));
      setServerError("");
    };
  }

  function markTouched(key) {
    return () => setTouched((prev) => ({ ...prev, [key]: true }));
  }

  function errorFor(key) {
    return touched[key] ? errors[key] : undefined;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setTouched({ name: true, email: true, password: true, passwordConfirm: true });
    if (!isValid) return;

    setServerError("");
    setSubmitting(true);
    try {
      await register({
        name: form.name.trim(),
        email: form.email.trim().toLowerCase(),
        password: form.password,
        role: form.role,
      });
      // 가입 직후 바로 로그인시킨다 — 방금 입력한 걸 로그인 화면에서 또 치게 하지 않는다.
      const { data } = await login({ email: form.email.trim().toLowerCase(), password: form.password });
      saveSession(data.access_token, data.user);
      navigate(homePathFor(data.user), { replace: true });
    } catch (err) {
      setServerError(err.userMessage || "가입에 실패했습니다");
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <span className="auth-title">회원가입</span>
        <p className="auth-sub" style={{ marginTop: 8 }}>
          이메일 인증 없이 바로 시작합니다
        </p>

        <form className="card" onSubmit={handleSubmit} noValidate>
          <Field label="이름" error={errorFor("name")}>
            {(props) => (
              <input
                {...props}
                type="text"
                placeholder="홍길동"
                value={form.name}
                onChange={update("name")}
                onBlur={markTouched("name")}
              />
            )}
          </Field>

          <Field
            label="이메일"
            hint="로그인할 때 쓰는 아이디입니다"
            error={errorFor("email")}
          >
            {(props) => (
              <input
                {...props}
                type="email"
                placeholder="name@company.com"
                value={form.email}
                onChange={update("email")}
                onBlur={markTouched("email")}
                autoComplete="email"
              />
            )}
          </Field>

          <Field
            label="비밀번호"
            hint="영문·숫자·기호 8자 이상 (한글은 사용할 수 없습니다)"
            error={errorFor("password")}
          >
            {(props) => (
              <input
                {...props}
                type="password"
                placeholder="8자 이상 입력하세요"
                value={form.password}
                onChange={update("password")}
                onBlur={markTouched("password")}
                autoComplete="new-password"
              />
            )}
          </Field>

          <Field label="비밀번호 확인" error={errorFor("passwordConfirm")}>
            {(props) => (
              <input
                {...props}
                type="password"
                placeholder="한 번 더 입력하세요"
                value={form.passwordConfirm}
                onChange={update("passwordConfirm")}
                onBlur={markTouched("passwordConfirm")}
                autoComplete="new-password"
              />
            )}
          </Field>

          <div className="field">
            <label>역할</label>
            <div className="radio-row">
              <label>
                <input
                  type="radio"
                  name="role"
                  value="newcomer"
                  checked={form.role === "newcomer"}
                  onChange={update("role")}
                />
                신입사원
              </label>
              <label>
                <input
                  type="radio"
                  name="role"
                  value="mentor"
                  checked={form.role === "mentor"}
                  onChange={update("role")}
                />
                사수
              </label>
            </div>
          </div>

          {serverError && <div className="banner banner-error">{serverError}</div>}

          <Button type="submit" variant="primary" block disabled={!isValid || submitting}>
            {submitting ? "가입 중…" : "가입하기"}
          </Button>
          {!isValid && (
            <p className="hint" style={{ textAlign: "center", marginTop: 8 }}>
              모든 항목을 채우고 비밀번호가 일치해야 눌립니다
            </p>
          )}

          <div className="auth-links">
            <span>이미 계정이 있으신가요?</span>
            <Link to="/login">로그인</Link>
          </div>
        </form>
      </div>
    </div>
  );
}

export default RegisterPage;
