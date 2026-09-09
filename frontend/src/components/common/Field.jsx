import { useId } from "react";

/**
 * 라벨 + 입력 + 힌트/에러 한 묶음.
 *
 * error가 있으면 힌트 대신 에러만 보여준다 — 둘 다 띄우면 어느 쪽을 고쳐야 하는지
 * 흐려진다. 입력 요소에는 aria-invalid를 내려서 테두리 색과 스크린리더 안내가
 * 함께 바뀌게 한다.
 */
function Field({ label, hint, error, children, htmlFor }) {
  const generatedId = useId();
  const inputId = htmlFor || generatedId;

  return (
    <div className="field">
      <label htmlFor={inputId}>{label}</label>
      {typeof children === "function"
        ? children({ id: inputId, "aria-invalid": error ? true : undefined })
        : children}
      {error ? (
        <p className="error">{error}</p>
      ) : hint ? (
        <p className="hint">{hint}</p>
      ) : null}
    </div>
  );
}

export default Field;
