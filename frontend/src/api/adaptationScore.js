import { parseServerDate } from "./datetime";

/**
 * 적응 지표 점수 (사수 리포트 전용).
 *
 * 리포트의 신호 4개는 단위가 제각각이라(질문 건수, 항목 목록, 전후반 비교) 한눈에 비교가
 * 안 된다. 여기서는 그 신호와 업무 목록·체크리스트를 0~100점 다섯 축으로 옮기고, 평균을
 * 종합 점수로 쓴다. 서버 호출이나 LLM 없이 이미 받아온 데이터만으로 계산한다.
 *
 * 점수 기준은 검증된 척도가 아니라 우리가 정한 규칙이다. 그래서 화면에 축마다 계산 방식을
 * 함께 보여준다 — 사수가 "왜 이 점수인지"를 되짚을 수 있어야 한다.
 *
 * 계산할 재료가 없는 축은 null로 두고 평균에서 뺀다(0점으로 치면 데이터가 없는 것이 나쁜
 * 신호처럼 보인다).
 */

export const SCORE_AXES = [
  {
    key: "depth",
    label: "질문 깊이",
    formula: "판단·심화 질문 ÷ 전체 질문",
    meaning: "단순 확인을 넘어서는 질문을 하는지",
    strength: "단순 확인을 넘어 판단이 필요한 질문을 하고 있습니다.",
    concern: "아직 사실을 확인하는 질문 위주로 묻고 있습니다.",
  },
  {
    key: "coverage",
    label: "업무 범위",
    formula: "질문이 닿은 대분류 ÷ 전체 대분류",
    meaning: "문서를 고르게 보고 있는지",
    strength: "문서의 여러 업무를 고르게 살펴보고 있습니다.",
    concern: "질문이 일부 업무에만 몰려 있습니다.",
  },
  {
    key: "alignment",
    label: "이해 일치도",
    formula: "완료 후 같은 업무를 다시 물은 정도 — 첫 질문 1건은 정상으로 보고 2건째부터 감점, 4건 이상이면 0점",
    meaning: "체크한 만큼 이해했는지",
    strength: "완료로 체크한 업무를 다시 묻지 않습니다.",
    concern: "완료로 체크한 업무를 이후에도 다시 묻고 있습니다.",
  },
  {
    key: "continuity",
    label: "질문 지속성",
    formula: "기간 뒤쪽 절반 질문 ÷ 앞쪽 절반 질문 (최대 100)",
    meaning: "질문이 끊기지 않고 이어지는지",
    strength: "질문이 끊기지 않고 꾸준히 이어집니다.",
    concern: "기간 뒤쪽 절반에 질문이 크게 줄었습니다.",
  },
  {
    key: "progress",
    label: "진행도",
    formula: "기간 말까지 완료한 항목 ÷ 전체 항목",
    meaning: "체크리스트를 진행하고 있는지",
    strength: "체크리스트를 순조롭게 진행하고 있습니다.",
    concern: "체크리스트 진행이 더딥니다.",
  },
];

const pct = (ratio) => Math.round(Math.max(0, Math.min(1, ratio)) * 100);

/**
 * @param report    AdaptationReport (sections 포함)
 * @param chapters  배정 문서의 DocumentChapter 목록
 * @param checklist 신입의 ChecklistItem 목록
 * @returns {{ axes: Record<string, number|null>, basis: Record<string, string>, total: number|null }}
 */
export function computeAdaptationScore(report, chapters, checklist) {
  const data = Object.fromEntries(
    (report?.sections || []).map((s) => [s.signal_type, s.data || {}]),
  );
  const growth = data.growth_curve || {};
  const counts = growth.counts || {};
  const questions = growth.total || 0;
  const heat = data.chapter_heatmap?.counts || {};
  const gapItems = data.gap_task?.gap_items || [];
  const silence = data.silence_risk || {};

  // 체크리스트는 현재 상태를 받아오므로, 리포트 기간이 끝난 시점까지 완료한 것만 센다.
  // 항목에 생성 시각이 없어 기간 이후에 추가된 항목도 분모(전체)에 들어간다 — 알려진 한계.
  const periodEnd = parseServerDate(report?.period_end);
  const done = (checklist || []).filter((item) => {
    const at = parseServerDate(item.completed_at);
    return at && periodEnd && at <= periodEnd;
  });

  // 소분류에 달린 질문은 그 대분류로 묶어서 센다.
  const parentOf = new Map(chapters.map((c) => [c.chapter_id, c.parent_id || c.chapter_id]));
  const tops = new Set(chapters.filter((c) => !c.parent_id).map((c) => c.chapter_id));
  const touched = new Set(
    Object.keys(heat)
      .map((id) => parentOf.get(id) || id)
      .filter((id) => tops.has(id)),
  );

  const axes = {
    depth: questions ? pct(((counts.judgment || 0) + (counts.advanced || 0)) / questions) : null,
    coverage: tops.size ? pct(touched.size / tops.size) : null,
    // 서버의 gap_task는 완료 후 같은 업무 질문이 1건만 있어도 그 항목을 센다. 그대로 비율로
    // 쓰면 "읽어보기를 체크하고 한 번 더 물어본" 자연스러운 행동까지 불일치가 되어 점수가
    // 0 아니면 100으로만 갈린다. 그래서 첫 질문 1건은 허용하고, 2건째부터 1/3씩 감점한다.
    alignment: done.length
      ? pct(
          1 -
            done.reduce((sum, item) => {
              const asked =
                gapItems.find((g) => g.title === item.title)?.question_count_after_complete || 0;
              return sum + Math.min(Math.max(asked - 1, 0), 3) / 3;
            }, 0) /
              done.length,
        )
      : null,
    continuity: silence.first_half_questions
      ? pct(silence.second_half_questions / silence.first_half_questions)
      : null,
    progress: checklist?.length ? pct(done.length / checklist.length) : null,
  };

  // 점수 옆에 붙이는 근거 숫자 — 표본이 작으면(완료 2개 등) 점수를 그만큼 가볍게 읽게 한다.
  const basis = {
    depth: `질문 ${questions}건 기준`,
    coverage: `대분류 ${tops.size}개 중 ${touched.size}개`,
    alignment: `완료 ${done.length}개 기준`,
    continuity:
      silence.first_half_questions !== undefined
        ? `앞 ${silence.first_half_questions}건 → 뒤 ${silence.second_half_questions}건`
        : "기간 내 질문 없음",
    progress: `${done.length} / ${(checklist || []).length}개 완료`,
  };

  const values = Object.values(axes).filter((v) => v !== null);
  const total = values.length
    ? Math.round(values.reduce((sum, v) => sum + v, 0) / values.length)
    : null;

  return { axes, basis, total };
}
