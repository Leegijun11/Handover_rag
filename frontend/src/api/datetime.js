/**
 * 서버 시각 다루기.
 *
 * 백엔드는 UTC로 계산한 값을 MySQL DATETIME에 넣는다 — `datetime.now(timezone.utc)`로
 * 만든 값을 PyMySQL이 tzinfo만 떼고 저장하는 구조라, 저장되는 건 "UTC 벽시계 시각"이다.
 * 그래서 조회 응답은 "2026-09-10T05:30:00"처럼 오프셋이 없는 문자열로 온다.
 *
 * 이걸 new Date()에 그대로 넣으면 자바스크립트가 로컬 시각으로 읽어서 한국에서는
 * 9시간이 밀린다. 읽을 때는 UTC로 못박고(Z를 붙여서), 보낼 때는 반대로 오프셋을 떼서
 * 서버가 쓰는 기준에 맞춘다.
 *
 * 오프셋이 붙어 오는 경우도 하나 있다 — POST /checklist/{id}/complete 응답만
 * DB를 다시 읽지 않고 커밋 직전의 파이썬 객체를 그대로 직렬화해서 "+00:00"이 붙는다.
 * 그래서 무조건 Z를 붙이면 안 되고, 오프셋 유무를 보고 갈라야 한다.
 */

const HAS_OFFSET = /(Z|[+-]\d{2}:?\d{2})$/;

/** 서버가 준 값 -> Date. 오프셋이 없으면 UTC로 해석한다. */
export function parseServerDate(value) {
  if (!value) return null;
  const text = typeof value === "string" ? value : String(value);
  const date = new Date(HAS_OFFSET.test(text) ? text : `${text}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Date -> 서버로 보낼 문자열. 오프셋 없는 UTC 형식("2026-09-10T05:30:00").
 *
 * toISOString()을 그대로 보내면 끝에 Z가 붙어 서버가 tz-aware로 파싱하는데,
 * report.py가 DB에서 읽은 naive 값과 그걸 비교하다가 500이 난다 (조장님 확인 대기 중).
 * 오프셋을 떼고 보내면 서버가 고쳐지기 전에도, 고쳐진 뒤에도 안전하다.
 */
export function toServerDate(date) {
  return date.toISOString().slice(0, 19);
}

function pad(n) {
  return String(n).padStart(2, "0");
}

/** "2026-09-10" (로컬 기준) */
export function formatDate(value) {
  const date = parseServerDate(value);
  if (!date) return "-";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** "2026-09-10 14:20" (로컬 기준) */
export function formatDateTime(value) {
  const date = parseServerDate(value);
  if (!date) return "-";
  return `${formatDate(value)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
