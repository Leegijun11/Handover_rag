import { useCallback, useEffect, useState } from "react";

import { getCurrentUser } from "../../api/session";
import { formatDate, formatDateTime, parseServerDate, toServerDate } from "../../api/datetime";
import { getChapters, listMyDocuments } from "../../services/router/document";
import { getChecklist } from "../../services/router/checklist";
import { SCORE_AXES, computeAdaptationScore } from "../../api/adaptationScore";
import { generateReport, getReportHistory } from "../../services/router/report";
import NewcomerPicker from "../../components/hr/NewcomerPicker";
import { DonutChart, RadarChart } from "../../components/hr/ReportCharts";
import Button from "../../components/common/Button";

/**
 * 리포트 관리 (guidelines 3-6, 4-3). 사수 전용 — 신입 화면에는 노출하지 않는다.
 *
 * 목록 -> 상세 두 단계 화면으로 구성한다 (신설). 예전엔 최신 리포트를 곧장 보여주고
 * 그 아래에 "생성 이력" 표를 곁다리로 붙였는데, 신입 한 명한테 리포트가 여러 개
 * 쌓이면 "지금 뭘 보고 있는지"가 헷갈렸다 — 목록에서 날짜로 먼저 고르고 들어가는
 * 흐름이 더 명확하다.
 *
 * GET /report/{newcomer_id}/history가 이미 생성 시각 역순 + sections 전체를 포함해서
 * 내려주므로(report.py), 최신 리포트도 이 목록의 첫 번째 항목으로 취급하고 별도
 * GET /report/{newcomer_id}는 부르지 않는다 — 같은 데이터를 두 번 받을 이유가 없다.
 *
 * 서버는 sections의 순서를 보장하지 않는다(관계에 정렬 기준이 없어서 DB가 주는 대로 온다).
 * 리포트를 다시 만들 때마다 카드 위치가 바뀌면 지난 리포트와 비교할 수 없으므로
 * 아래 SIGNAL_ORDER로 프론트에서 고정한다.
 */

const SIGNAL_ORDER = ["growth_curve", "chapter_heatmap", "gap_task", "silence_risk"];

const SIGNAL_TITLE = {
  growth_curve: "질문 성장 곡선",
  chapter_heatmap: "영역별 히트맵",
  gap_task: "완료–이해 불일치",
  silence_risk: "침묵 위험",
};

const QUESTION_TYPE_LABEL = {
  fact: "사실 확인",
  procedure: "절차",
  judgment: "판단",
  advanced: "심화",
};

// report.py의 MIN_REGENERATE_INTERVAL과 같은 값. 이 시간 안에 다시 부르면 서버가 429를 준다.
const REGENERATE_LOCK_MS = 5 * 60 * 1000;

function sortSections(sections) {
  return [...(sections || [])].sort(
    (a, b) => SIGNAL_ORDER.indexOf(a.signal_type) - SIGNAL_ORDER.indexOf(b.signal_type),
  );
}

/** 질문 유형 4개를 가로 막대로. 지난 리포트 값은 숫자로만 곁들인다. */
function TypeBars({ counts, previousCounts }) {
  const entries = Object.entries(QUESTION_TYPE_LABEL).map(([key, label]) => ({
    label,
    value: counts[key] || 0,
    previous: previousCounts ? previousCounts[key] || 0 : null,
  }));
  const max = entries.reduce((m, e) => Math.max(m, e.value), 0);
  if (max === 0) {
    return <div className="empty" style={{ padding: 20 }}>기간 내 질문 없음</div>;
  }
  return (
    <div className="bars">
      {entries.map((e) => (
        <div className="bar-row" key={e.label}>
          <div className="bar-head">
            <span className="bar-label">{e.label}</span>
            {e.previous !== null && <span className="bar-prev">지난 {e.previous}</span>}
            <span className="num">{e.value}건</span>
          </div>
          <span className="bar">
            <i style={{ width: `${Math.round((e.value / max) * 100)}%` }} />
          </span>
        </div>
      ))}
    </div>
  );
}

function SignalBody({ section, previousSection, chapterTitleOf }) {
  const data = section.data || {};

  if (section.signal_type === "growth_curve") {
    return (
      <TypeBars counts={data.counts || {}} previousCounts={previousSection?.data?.counts} />
    );
  }

  if (section.signal_type === "chapter_heatmap") {
    const counts = data.counts || {};
    const entries = Object.entries(counts).map(([chapterId, value]) => ({
      label: chapterTitleOf(chapterId),
      value,
    }));
    return <DonutChart entries={entries} />;
  }

  if (section.signal_type === "gap_task") {
    const gaps = data.gap_items || [];
    if (!gaps.length) {
      return <div className="empty" style={{ padding: 20 }}>불일치가 감지된 항목 없음</div>;
    }
    return (
      <table className="rpt-table compact">
        <thead>
          <tr>
            <th>완료 체크한 항목</th>
            <th className="num">이후 질문</th>
          </tr>
        </thead>
        <tbody>
          {gaps.map((gap, index) => (
            <tr key={`${gap.title}-${index}`}>
              <td>{gap.title}</td>
              <td className="num warn">{gap.question_count_after_complete}건</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  // silence_risk는 데이터 모양이 두 가지다. 기간 내 질문이 하나도 없으면 전반부/후반부
  // 숫자 없이 reason만 온다 — 그 경우를 따로 그리지 않으면 화면이 비어버린다.
  if (data.first_half_questions === undefined) {
    return (
      <div className="empty" style={{ padding: 20 }}>
        기간 내 질문이 없어 급감 여부를 계산하지 않았습니다
      </div>
    );
  }
  return (
    <div className="stat-row">
      <div className="stat">
        <div className="n">{data.first_half_questions}</div>
        <div className="k">전반부 질문</div>
      </div>
      <div className="stat">
        <div className="n">{data.second_half_questions}</div>
        <div className="k">후반부 질문</div>
      </div>
      <div className="stat">
        <div className={`n ${data.dropped_sharply ? "warn" : "good"}`}>
          {data.dropped_sharply ? "급감" : "정상"}
        </div>
        <div className="k">질문 추이</div>
      </div>
    </div>
  );
}

function Delta({ value }) {
  if (value === null || value === undefined) return <span className="delta none">—</span>;
  if (value === 0) return <span className="delta flat">변화 없음</span>;
  // 색만으로 읽히지 않게 화살표와 숫자를 함께 쓴다.
  return (
    <span className={`delta ${value > 0 ? "up" : "down"}`}>
      {value > 0 ? "▲" : "▼"} {Math.abs(value)}
    </span>
  );
}

/**
 * 규칙으로 뽑는 핵심 발견. 가장 높은 지표 하나를 강점으로, 60점 미만인 지표를 낮은 순으로
 * 최대 두 개까지 확인 필요로 둔다. LLM을 부르지 않으므로 기준이 늘 같다.
 */
function findingsOf(axes) {
  const scored = SCORE_AXES.map((axis) => ({ ...axis, score: axes[axis.key] })).filter(
    (a) => a.score !== null,
  );
  const best = [...scored].sort((a, b) => b.score - a.score)[0];
  const weak = scored
    .filter((a) => a.score < 60)
    .sort((a, b) => a.score - b.score)
    .slice(0, 2);
  return { best: best && best.score >= 60 ? best : null, weak };
}

/**
 * 리포트 상세 — 문서형 구성.
 *
 * 인사 리포트에서 흔히 쓰는 순서를 따른다: 표제(누구의, 어느 기간) → 요약(종합 점수와
 * 핵심 발견) → 지표별 점수 → 근거 데이터 → 산정 기준. 결론을 먼저 보고, 필요할 때만
 * 아래로 내려가 근거를 확인하게 한다.
 */
function ReportDetail({
  report,
  previousReport,
  chapters,
  checklist,
  newcomerName,
  mentorName,
  documentLabel,
  chapterTitleOf,
  onBack,
}) {
  const sections = sortSections(report.sections);
  const previousOf = (type) =>
    (previousReport?.sections || []).find((s) => s.signal_type === type);

  const current = computeAdaptationScore(report, chapters, checklist);
  const previous = previousReport
    ? computeAdaptationScore(previousReport, chapters, checklist)
    : null;
  const totalDelta =
    previous && previous.total !== null && current.total !== null
      ? current.total - previous.total
      : null;
  const { best, weak } = findingsOf(current.axes);

  const radarAxes = SCORE_AXES.map((axis) => ({
    label: axis.label,
    value: current.axes[axis.key] ?? 0,
    previous: previous ? previous.axes[axis.key] ?? 0 : undefined,
  }));

  return (
    <article className="rpt">
      <button type="button" className="link-back" onClick={onBack}>
        ← 목록으로
      </button>

      <header className="rpt-head">
        <p className="rpt-kicker">신입 적응도 리포트</p>
        <h4 className="rpt-title">{newcomerName || "신입"}</h4>
        <dl className="rpt-meta">
          <div>
            <dt>분석 기간</dt>
            <dd>
              {formatDate(report.period_start)} ~ {formatDate(report.period_end)}
            </dd>
          </div>
          <div>
            <dt>담당 사수</dt>
            <dd>{mentorName || "-"}</dd>
          </div>
          <div>
            <dt>배정 문서</dt>
            <dd>{documentLabel || "-"}</dd>
          </div>
          <div>
            <dt>생성 일시</dt>
            <dd>{formatDateTime(report.generated_at)}</dd>
          </div>
        </dl>
      </header>

      <section className="rpt-sec">
        <h5 className="rpt-sec-title">
          <span>01</span>종합 요약
        </h5>
        <div className="rpt-overview">
          <div className="rpt-score">
            <p className="rpt-score-label">종합 점수</p>
            <p className="rpt-score-value">
              {current.total ?? "-"}
              <small>/ 100</small>
            </p>
            <p className="rpt-score-delta">
              {previous ? (
                <>
                  <Delta value={totalDelta} />
                  <span className="muted">지난 리포트 {previous.total ?? "-"}점 대비</span>
                </>
              ) : (
                <span className="muted">첫 리포트 — 비교할 이전 리포트가 없습니다</span>
              )}
            </p>

            <ul className="rpt-findings">
              {best && (
                <li className="good">
                  <b>강점</b>
                  <span>
                    <em>
                      {best.label} {best.score}점
                    </em>
                    {best.strength}
                  </span>
                </li>
              )}
              {weak.map((axis) => (
                <li className="warn" key={axis.key}>
                  <b>확인 필요</b>
                  <span>
                    <em>
                      {axis.label} {axis.score}점
                    </em>
                    {axis.concern}
                  </span>
                </li>
              ))}
              {!weak.length && (
                <li className="neutral">
                  <b>확인 필요</b>
                  <span>60점 미만인 지표가 없습니다.</span>
                </li>
              )}
            </ul>
          </div>

          <div className="rpt-radar">
            <RadarChart axes={radarAxes} max={100} unit="점" />
          </div>
        </div>
      </section>

      <section className="rpt-sec">
        <h5 className="rpt-sec-title">
          <span>02</span>지표별 점수
        </h5>
        <div className="table-scroll">
          <table className="rpt-table">
            <thead>
              <tr>
                <th>지표</th>
                <th className="score-col">점수</th>
                <th className="num">지난 대비</th>
                <th>산정 기준</th>
              </tr>
            </thead>
            <tbody>
              {SCORE_AXES.map((axis) => {
                const score = current.axes[axis.key];
                const prev = previous?.axes[axis.key];
                const delta =
                  score !== null && prev !== null && prev !== undefined ? score - prev : null;
                return (
                  <tr key={axis.key}>
                    <td>
                      <b>{axis.label}</b>
                      <div className="sub">{axis.meaning}</div>
                    </td>
                    <td className="score-col">
                      {score === null ? (
                        <span className="muted">데이터 없음</span>
                      ) : (
                        <div className="score-bar">
                          <span className="bar">
                            <i
                              className={score < 60 ? "low" : undefined}
                              style={{ width: `${score}%` }}
                            />
                          </span>
                          <span className="score-num">{score}</span>
                        </div>
                      )}
                    </td>
                    <td className="num">
                      <Delta value={previous ? delta : null} />
                    </td>
                    <td className="sub">{axis.formula}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rpt-sec">
        <h5 className="rpt-sec-title">
          <span>03</span>근거 데이터
        </h5>
        <div className="rpt-evidence">
          {sections.map((section) => (
            <div className="rpt-card" key={section.signal_type}>
              <h6>{SIGNAL_TITLE[section.signal_type] || section.signal_type}</h6>
              <SignalBody
                section={section}
                previousSection={previousOf(section.signal_type)}
                chapterTitleOf={chapterTitleOf}
              />
              <p className="rpt-card-note">{section.summary}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="rpt-foot">
        <b>산정 기준 안내</b> 지표 점수는 이 리포트의 질문 기록과 체크리스트로 계산한 0~100점이며,
        종합 점수는 계산할 수 있는 지표의 평균입니다. 데이터가 없는 지표는 평균에서 제외합니다.
        체크리스트에는 생성 시각이 없어 분석 기간 이후 추가된 항목도 진행도의 전체 항목 수에
        포함됩니다. 점수는 적응 상태를 살피기 위한 참고 지표이며 평가 용도가 아닙니다.
      </footer>
    </article>
  );
}

function ReportPage() {
  const mentor = getCurrentUser();

  const [assignment, setAssignment] = useState(null);
  const [history, setHistory] = useState([]);
  const [chapters, setChapters] = useState([]);
  // 점수 계산(완료 항목·진행도)과 표제부(배정 문서 이름)에 쓴다. 둘 다 조회만 한다.
  const [checklist, setChecklist] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  // 목록 -> 상세. selectedReport가 있으면 상세를 보여준다.
  const [selectedReport, setSelectedReport] = useState(null);

  const newcomerId = assignment?.newcomer_id;
  const documentId = assignment?.document_id;
  const latest = history[0] || null;

  const load = useCallback(async () => {
    if (!newcomerId) return;
    setLoading(true);
    setError("");
    try {
      const { data } = await getReportHistory(newcomerId);
      setHistory(data || []);
    } catch (err) {
      setError(err.userMessage || "리포트 목록을 불러오지 못했습니다");
      setHistory([]);
    }
    setLoading(false);
  }, [newcomerId]);

  useEffect(() => {
    setSelectedReport(null); // 신입을 바꾸면 상세 화면에 남아있지 않고 목록부터 다시 본다
    load();
  }, [load]);

  // 히트맵의 chapter_id를 업무 제목으로 바꿔 보여주기 위한 조회. MySQL만 읽는다.
  useEffect(() => {
    if (!documentId) return undefined;
    let cancelled = false;
    getChapters(documentId)
      .then(({ data }) => !cancelled && setChapters(data || []))
      .catch(() => !cancelled && setChapters([]));
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  useEffect(() => {
    if (!newcomerId) return undefined;
    let cancelled = false;
    getChecklist(newcomerId)
      .then(({ data }) => !cancelled && setChecklist(data || []))
      .catch(() => !cancelled && setChecklist([]));
    return () => {
      cancelled = true;
    };
  }, [newcomerId]);

  useEffect(() => {
    let cancelled = false;
    listMyDocuments(mentor.user_id)
      .then(({ data }) => !cancelled && setDocuments(data || []))
      .catch(() => !cancelled && setDocuments([]));
    return () => {
      cancelled = true;
    };
  }, [mentor.user_id]);

  const generatedAt = latest ? parseServerDate(latest.generated_at) : null;
  const lockUntil = generatedAt ? generatedAt.getTime() + REGENERATE_LOCK_MS : 0;
  const lockSecondsLeft = Math.max(0, Math.ceil((lockUntil - now) / 1000));

  // 잠금이 걸려 있는 동안에만 1초마다 다시 그린다.
  useEffect(() => {
    if (lockSecondsLeft <= 0) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [lockSecondsLeft]);

  function chapterTitleOf(chapterId) {
    // 재배정으로 문서가 바뀌면(guidelines 3-1) 히트맵이 가리키는 챕터가 지금 배정된
    // 문서의 목록엔 없을 수 있다 — UUID를 그대로 보여주지 않는다.
    return (
      chapters.find((c) => c.chapter_id === chapterId)?.title ||
      "삭제되었거나 문서가 바뀐 업무"
    );
  }

  async function handleGenerate() {
    if (!newcomerId || generating) return;
    setGenerating(true);
    setError("");
    try {
      // 기간 기본값 (guidelines 3-6): 이전 리포트가 있으면 그 period_end부터, 처음이면 배정일부터.
      // 오프셋 없는 형식으로 보낸다 — 자세한 이유는 api/datetime.js 참고.
      const periodEnd = toServerDate(new Date());
      const previousEnd = latest ? parseServerDate(latest.period_end) : null;
      const assignedAt = parseServerDate(assignment?.assigned_at);
      const start = previousEnd || assignedAt || new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);

      await generateReport(newcomerId, toServerDate(start), periodEnd);
      const { data } = await getReportHistory(newcomerId);
      setHistory(data || []);
      // 방금 만든 걸 바로 상세로 보여준다 — 목록에서 한 번 더 찾아 누르게 하지 않는다.
      setSelectedReport(data?.[0] || null);
      setNow(Date.now());
    } catch (err) {
      setError(err.userMessage || "리포트를 만들지 못했습니다");
      if (err.response?.status === 429) setNow(Date.now());
    } finally {
      setGenerating(false);
    }
  }

  return (
    <>
      <h3 className="page-title">리포트 관리</h3>
      <p className="page-desc">담당 신입의 질문·체크리스트 기록에서 뽑은 적응 신호입니다.</p>

      <NewcomerPicker mentorId={mentor.user_id} value={assignment} onChange={setAssignment} />

      {assignment && (
        <>
          <div className="banner banner-warn">
            이 화면은 사수에게만 보입니다. 신입 화면에는 리포트가 노출되지 않습니다.
          </div>

          {error && <div className="banner banner-error">{error}</div>}

          {selectedReport ? (
            <ReportDetail
              report={selectedReport}
              // history는 생성 시각 역순이라 바로 다음 항목이 직전 리포트다.
              previousReport={
                history[history.findIndex((r) => r.report_id === selectedReport.report_id) + 1]
              }
              chapters={chapters}
              checklist={checklist}
              newcomerName={assignment?.name}
              mentorName={mentor?.name}
              documentLabel={documents.find((d) => d.document_id === documentId)?.label}
              chapterTitleOf={chapterTitleOf}
              onBack={() => setSelectedReport(null)}
            />
          ) : (
            <>
              <div className="report-head">
                <div>
                  <p className="page-desc" style={{ margin: 0 }}>
                    {history.length > 0
                      ? `생성된 리포트 ${history.length}건`
                      : "아직 생성된 리포트가 없습니다."}
                  </p>
                </div>
                <div className="actions" style={{ margin: 0 }}>
                  <Button
                    variant="primary"
                    onClick={handleGenerate}
                    disabled={generating || lockSecondsLeft > 0}
                  >
                    {generating
                      ? "만드는 중…"
                      : lockSecondsLeft > 0
                        ? `${Math.ceil(lockSecondsLeft / 60)}분 뒤 다시 생성`
                        : latest
                          ? "새 리포트 만들기"
                          : "첫 리포트 만들기"}
                  </Button>
                </div>
              </div>

              {generating && (
                <div className="banner banner-info">
                  질문 기록과 체크리스트를 모아 신호 4개를 계산하고 있습니다. 20초쯤 걸립니다.
                </div>
              )}

              {!generating && lockSecondsLeft > 0 && (
                <div className="banner banner-info">
                  리포트는 5분에 한 번만 만들 수 있습니다. 방금 만든 결과는 목록 맨 위에 있습니다.
                </div>
              )}

              {loading ? (
                <div className="empty">불러오는 중…</div>
              ) : history.length === 0 ? (
                <div className="empty">
                  질문과 체크리스트가 어느 정도 쌓인 뒤에 만들면 더 정확합니다.
                </div>
              ) : (
                <div className="card">
                  <p className="card-title">생성 날짜별 리포트</p>
                  <table>
                    <thead>
                      <tr>
                        <th>생성 시각</th>
                        <th>기간</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {history.map((row, index) => (
                        <tr key={row.report_id}>
                          <td>
                            {formatDateTime(row.generated_at)}
                            {index === 0 && (
                              <span className="badge badge-manual" style={{ marginLeft: 6 }}>
                                최신
                              </span>
                            )}
                          </td>
                          <td>
                            {formatDate(row.period_start)} ~ {formatDate(row.period_end)}
                          </td>
                          <td style={{ textAlign: "right" }}>
                            <Button size="sm" onClick={() => setSelectedReport(row)}>
                              자세히 보기
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </>
      )}
    </>
  );
}

export default ReportPage;
