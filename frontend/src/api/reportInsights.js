import { SCORE_AXES } from "./adaptationScore";
import { formatDate, parseServerDate } from "./datetime";

/**
 * 리포트의 "그래서 사수가 무엇을 하면 되나"를 만드는 규칙.
 *
 * 점수만 보여주면 사수는 상태를 알 뿐 행동을 정하지 못한다. 여기서는 점수가 낮은 지표마다
 * 실제 항목 이름과 횟수를 넣은 권장 조치 문장을 만든다. LLM을 부르지 않으므로 같은 데이터면
 * 늘 같은 결과가 나오고, 문장에 들어간 숫자는 화면 아래 근거에서 그대로 확인할 수 있다.
 */

// 이 점수 미만이면 주의로 본다. 지표별 상태 칩과 권장 조치가 같은 기준을 쓴다.
export const CONCERN_BELOW = 60;

// 배정 직후에는 사실 확인 질문이 많고, 몇 개 업무만 묻고, 체크리스트도 거의 안 끝낸 게 정상이다.
// 이 기간 안에는 질문 깊이·업무 범위·진행도를 권장 조치로 올리지 않는다 — 올리면 1주차 신입이
// 전부 "주의"로 보인다. 반복 질문과 질문 급감은 시기와 무관하게 짚는다.
const EARLY_DAYS = 14;
const EARLY_EXEMPT = new Set(["depth", "coverage", "progress"]);

// 질문 흐름·진행도는 높다고 좋은 게 아니라서 강점 후보에서 뺀다. 반복 질문이 많아도 흐름 점수는
// 올라가므로, 이걸 강점으로 뽑으면 "같은 걸 계속 묻는 신입"이 오히려 칭찬받는 모순이 생긴다.
const STRENGTH_CANDIDATES = new Set(["depth", "coverage", "alignment"]);

// 주의 지표가 여럿일 때 무엇을 먼저 말할지. 점수가 가장 낮은 순으로 두면 "질문 깊이 25점"처럼
// 시간이 지나면 자연히 나아지는 지표가 "완료한 업무를 3번씩 다시 묻는다" 같은 당장 손봐야 할
// 문제보다 앞에 온다. 사수가 이번 주에 개입해야 하는 순서대로 고정한다.
const URGENCY = ["alignment", "continuity", "coverage", "progress", "depth"];
const byUrgency = (a, b) => URGENCY.indexOf(a.key) - URGENCY.indexOf(b.key);

export function statusOf(score) {
  if (score === null || score === undefined) return "none";
  return score < CONCERN_BELOW ? "concern" : "good";
}

/** 리포트 기간 끝 기준 배정 후 경과 일수. 배정일을 모르면 null. */
function daysSinceAssigned(report, assignedAt) {
  const start = parseServerDate(assignedAt);
  const end = parseServerDate(report?.period_end);
  if (!start || !end) return null;
  return Math.floor((end - start) / 86400000);
}

function isEarly(report, assignedAt) {
  const days = daysSinceAssigned(report, assignedAt);
  return days !== null && days < EARLY_DAYS;
}

/** 질문이 한 번도 닿지 않은 대분류 업무. 소분류에 달린 질문은 대분류로 묶는다. */
export function untouchedChapters(report, chapters) {
  const heat =
    (report?.sections || []).find((s) => s.signal_type === "chapter_heatmap")?.data?.counts || {};
  const parentOf = new Map(chapters.map((c) => [c.chapter_id, c.parent_id || c.chapter_id]));
  const touched = new Set(Object.keys(heat).map((id) => parentOf.get(id) || id));
  return chapters.filter((c) => !c.parent_id && !touched.has(c.chapter_id));
}

/**
 * 권장 조치 — 주의 지표를 급한 순서(URGENCY)로 최대 3개.
 * 각 항목: { key, text }
 */
export function buildActions({ report, score, chapters, checklist, assignedAt }) {
  const data = Object.fromEntries((report?.sections || []).map((s) => [s.signal_type, s.data || {}]));
  const early = isEarly(report, assignedAt);
  const periodEnd = parseServerDate(report?.period_end);

  const makers = {
    alignment: () => {
      const top = [...(data.gap_task?.gap_items || [])]
        .filter((g) => g.question_count_after_complete >= 2)
        .sort((a, b) => b.question_count_after_complete - a.question_count_after_complete)[0];
      if (!top) return null;
      return `'${top.title}'을 완료로 체크했지만 이후에도 ${top.question_count_after_complete}번 더 물었습니다. 한 번 옆에서 같이 해보며 확인해주세요.`;
    },
    depth: () => {
      return "아직 사실을 확인하는 질문이 대부분입니다. 판단이 필요한 실제 사례를 하나 맡겨보세요.";
    },
    coverage: () => {
      const missing = untouchedChapters(report, chapters);
      if (!missing.length) return null;
      const names = missing.slice(0, 2).map((c) => `'${c.title}'`).join(", ");
      const more = missing.length > 2 ? ` 외 ${missing.length - 2}개` : "";
      return `${names}${more} 업무는 한 번도 묻지 않았습니다. 이 업무를 짧게 소개해주세요.`;
    },
    continuity: () => {
      const s = data.silence_risk || {};
      if (s.first_half_questions === undefined) return null;
      return `질문이 기간 앞쪽 ${s.first_half_questions}건에서 뒤쪽 ${s.second_half_questions}건으로 줄었습니다. 막힌 곳이 없는지 먼저 물어봐주세요.`;
    },
    progress: () => {
      const pending = (checklist || []).filter((item) => {
        const at = parseServerDate(item.completed_at);
        return !(at && periodEnd && at <= periodEnd);
      }).length;
      if (!pending) return null;
      return `체크리스트 ${pending}개가 남아 있습니다. 다음 주에 끝낼 항목을 함께 정해주세요.`;
    },
  };

  return SCORE_AXES.filter((axis) => statusOf(score.axes[axis.key]) === "concern")
    .filter((axis) => !(early && EARLY_EXEMPT.has(axis.key)))
    .sort(byUrgency)
    .map((axis) => ({ key: axis.key, text: makers[axis.key]() }))
    .filter((action) => action.text)
    .slice(0, 3);
}

/** 가장 좋은 지표 하나 — 질문 깊이·업무 범위·이해 일치도 중에서만 고른다. */
export function pickStrength(score) {
  return SCORE_AXES.filter((axis) => STRENGTH_CANDIDATES.has(axis.key))
    .map((axis) => ({ ...axis, value: score.axes[axis.key] }))
    .filter((axis) => axis.value !== null && axis.value >= 80)
    .sort((a, b) => b.value - a.value)[0] || null;
}

/**
 * 맨 위 한 줄 판정. 권장 조치의 첫 번째(가장 급한) 지표 문장을 쓰고, 없으면 — 배정 초기면
 * "아직 이르다", 아니면 "순조롭다"고 적는다. 초기에 "순조롭다"고 쓰면 데이터가 적어서
 * 안 잡힌 것을 좋은 신호로 착각하게 된다.
 */
export function buildHeadline({ actions, report, assignedAt }) {
  const worst = actions.length ? SCORE_AXES.find((axis) => axis.key === actions[0].key) : null;
  if (worst) return worst.concern;
  const days = daysSinceAssigned(report, assignedAt);
  if (days !== null && days < EARLY_DAYS) {
    return `배정 ${days + 1}일차라 아직 판단하기 이릅니다. 지금은 질문이 이어지는지만 살펴보세요.`;
  }
  return "특별히 짚어야 할 신호 없이 순조롭게 적응하고 있습니다.";
}

/** 체크리스트를 리포트 기간 말 기준 완료/미완료로 나눈다. */
export function splitChecklist(report, checklist) {
  const periodEnd = parseServerDate(report?.period_end);
  const done = [];
  const pending = [];
  [...(checklist || [])]
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
    .forEach((item) => {
      const at = parseServerDate(item.completed_at);
      if (at && periodEnd && at <= periodEnd) done.push({ ...item, doneLabel: formatDate(item.completed_at) });
      else pending.push(item);
    });
  return { done, pending };
}
