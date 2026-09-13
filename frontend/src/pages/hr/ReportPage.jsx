import { useCallback, useEffect, useState } from "react";

import { getCurrentUser } from "../../api/session";
import { formatDate, formatDateTime, parseServerDate, toServerDate } from "../../api/datetime";
import { getChapters, listMyDocuments } from "../../services/router/document";
import { getChecklist } from "../../services/router/checklist";
import { SCORE_AXES, computeAdaptationScore } from "../../api/adaptationScore";
import {
  buildActions,
  buildHeadline,
  pickStrength,
  splitChecklist,
  statusOf,
  untouchedChapters,
} from "../../api/reportInsights";
import { getChatLogs } from "../../services/router/chat";
import { generateReport, getReportHistory } from "../../services/router/report";
import NewcomerPicker from "../../components/hr/NewcomerPicker";
import { DonutChart, QuestionTimeline, RadarChart } from "../../components/hr/ReportCharts";
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
 * 서버는 sections의 순서를 보장하지 않는다. 상세 화면은 신호를 순서대로 나열하지 않고
 * SCORE_AXES의 지표 순서대로 그리므로 서버 순서에 영향을 받지 않는다.
 */

const QUESTION_TYPE_LABEL = {
  fact: "사실 확인",
  procedure: "절차",
  judgment: "판단",
  advanced: "심화",
};

// report.py의 MIN_REGENERATE_INTERVAL과 같은 값. 이 시간 안에 다시 부르면 서버가 429를 준다.
const REGENERATE_LOCK_MS = 5 * 60 * 1000;

/** 질문 유형 4개를 가로 막대로. 지난 리포트 값은 괄호로 곁들인다. */
function TypeBars({ counts, previousCounts }) {
  const entries = Object.entries(QUESTION_TYPE_LABEL).map(([key, label]) => ({
    label,
    value: counts[key] || 0,
    previous: previousCounts ? previousCounts[key] || 0 : null,
  }));
  const max = entries.reduce((m, e) => Math.max(m, e.value), 0);
  if (max === 0) {
    return <div className="empty" style={{ padding: 16 }}>기간 내 질문 없음</div>;
  }
  return (
    <div className="bars">
      {entries.map((e) => (
        <div className="bar-row" key={e.label}>
          <div className="bar-head">
            <span className="bar-label">{e.label}</span>
            <span className="num">
              {e.value}건
              {e.previous !== null && <span className="bar-prev"> (지난 리포트 {e.previous}건)</span>}
            </span>
          </div>
          <span className="bar">
            <i style={{ width: `${Math.round((e.value / max) * 100)}%` }} />
          </span>
        </div>
      ))}
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

const STATUS_LABEL = { good: "양호", concern: "주의", none: "데이터 부족" };

/** 지표 하나의 근거 — 지표와 신호를 1:1로 묶어서 같은 사실을 두 번 보여주지 않는다. */
function MetricEvidence({ axisKey, report, previousReport, chapters, checklist, chatTimes, chapterTitleOf }) {
  const data = Object.fromEntries((report.sections || []).map((s) => [s.signal_type, s.data || {}]));

  if (axisKey === "depth") {
    const prev = (previousReport?.sections || []).find((s) => s.signal_type === "growth_curve");
    return <TypeBars counts={data.growth_curve?.counts || {}} previousCounts={prev?.data?.counts} />;
  }

  if (axisKey === "coverage") {
    const counts = data.chapter_heatmap?.counts || {};
    const entries = Object.entries(counts).map(([id, value]) => ({ label: chapterTitleOf(id), value }));
    const missing = untouchedChapters(report, chapters);
    const total = data.growth_curve?.total || 0;
    const linked = entries.reduce((sum, e) => sum + e.value, 0);
    return (
      <>
        <DonutChart entries={entries} />
        {total > linked && (
          <p className="evidence-note">
            답을 찾지 못해 업무에 연결되지 않은 질문 {total - linked}건은 비중에서 제외했습니다.
          </p>
        )}
        {missing.length > 0 && (
          <p className="evidence-note">
            <b>아직 질문하지 않은 업무</b> {missing.map((c) => c.title).join(" · ")}
          </p>
        )}
      </>
    );
  }

  if (axisKey === "alignment") {
    const gaps = data.gap_task?.gap_items || [];
    if (!gaps.length) {
      return <div className="empty" style={{ padding: 16 }}>완료 후 다시 물은 항목 없음</div>;
    }
    return (
      <table className="rpt-table">
        <thead>
          <tr>
            <th>완료 체크한 항목</th>
            <th className="num">완료 후 질문</th>
          </tr>
        </thead>
        <tbody>
          {gaps.map((gap, index) => (
            <tr key={`${gap.title}-${index}`}>
              <td>{gap.title}</td>
              <td className={`num ${gap.question_count_after_complete >= 2 ? "warn" : ""}`}>
                {gap.question_count_after_complete}건
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  if (axisKey === "continuity") {
    const silence = data.silence_risk || {};
    const start = parseServerDate(report.period_start);
    const end = parseServerDate(report.period_end);
    if (silence.first_half_questions === undefined) {
      return <div className="empty" style={{ padding: 16 }}>기간 내 질문 없음</div>;
    }
    return (
      <>
        <QuestionTimeline
          times={chatTimes.filter((t) => t >= start && t <= end)}
          start={start}
          end={end}
          dropped={silence.dropped_sharply}
        />
        <p className="evidence-note">
          점선 앞 {silence.first_half_questions}건 · 뒤 {silence.second_half_questions}건 — 뒤쪽이
          앞쪽의 30% 이하로 줄면 급감으로 봅니다.
        </p>
      </>
    );
  }

  // progress
  const { done, pending } = splitChecklist(report, checklist);
  if (!done.length && !pending.length) {
    return <div className="empty" style={{ padding: 16 }}>체크리스트 없음</div>;
  }
  return (
    <ul className="progress-list">
      {done.map((item) => (
        <li key={item.item_id} className="done">
          <span className="mark" aria-label="완료">✓</span>
          <span className="title">{item.title}</span>
          <span className="when">{item.doneLabel}</span>
        </li>
      ))}
      {pending.map((item) => (
        <li key={item.item_id}>
          <span className="mark" aria-label="미완료" />
          <span className="title">{item.title}</span>
          <span className="when">미완료</span>
        </li>
      ))}
    </ul>
  );
}

// 지표 → 그 지표의 근거가 되는 서버 신호(해석 문장은 서버가 신호 단위로 만든다)
const SIGNAL_OF_AXIS = {
  depth: "growth_curve",
  coverage: "chapter_heatmap",
  alignment: "gap_task",
  continuity: "silence_risk",
};

/**
 * 리포트 상세.
 *
 * 구성: 표제 → 요약(한 줄 판정·종합 점수·권장 조치·오각형) → 지표별 분석 → 산정 기준.
 * 예전엔 같은 사실을 오각형·요약 문장·점수 표·근거 카드로 네 번 보여줬다. 지금은 지표 하나를
 * 한 블록에서 점수·근거·해석까지 한 번만 보여준다.
 */
function ReportDetail({
  report,
  previousReport,
  chapters,
  checklist,
  chatTimes,
  assignedAt,
  newcomerName,
  mentorName,
  documentLabel,
  chapterTitleOf,
  onBack,
}) {
  const current = computeAdaptationScore(report, chapters, checklist);
  const previous = previousReport ? computeAdaptationScore(previousReport, chapters, checklist) : null;
  const totalDelta =
    previous && previous.total !== null && current.total !== null ? current.total - previous.total : null;

  const actions = buildActions({ report, score: current, chapters, checklist, assignedAt });
  const strength = pickStrength(current);
  const headline = buildHeadline(current, actions);

  const radarAxes = SCORE_AXES.map((axis) => ({
    label: axis.label,
    value: current.axes[axis.key] ?? 0,
    previous: previous ? previous.axes[axis.key] ?? 0 : undefined,
  }));
  const summaryOf = (axisKey) =>
    (report.sections || []).find((s) => s.signal_type === SIGNAL_OF_AXIS[axisKey])?.summary;

  return (
    <article className="rpt">
      <button type="button" className="link-back" onClick={onBack}>
        ← 목록으로
      </button>

      <header className="rpt-head">
        <p className="rpt-kicker">
          신입 적응도 리포트 <span>사수 전용 · 신입에게 공개되지 않음</span>
        </p>
        <h4 className="rpt-title">{newcomerName || "신입"}</h4>
        {/* 라벨 칸 폭을 고정한 2×2 정보 표 — 값 길이가 제각각이어도 라벨과 값의 시작선이 맞는다 */}
        <dl className="rpt-meta">
          <dt>분석 기간</dt>
          <dd>
            {formatDate(report.period_start)} ~ {formatDate(report.period_end)}
          </dd>
          <dt>담당 사수</dt>
          <dd>{mentorName || "-"}</dd>
          <dt>배정 문서</dt>
          <dd title={documentLabel || ""}>{documentLabel || "-"}</dd>
          <dt>생성 일시</dt>
          <dd>{formatDateTime(report.generated_at)}</dd>
        </dl>
      </header>

      <section className="rpt-sec">
        <h5 className="rpt-sec-title">
          <span>01</span>요약
        </h5>

        <p className="rpt-verdict">{headline}</p>

        <div className="rpt-overview">
          <div className="rpt-score">
            <div className="rpt-score-row">
              <p className="rpt-score-value">
                {current.total ?? "-"}
                <small>/ 100</small>
              </p>
              <div className="rpt-score-side">
                <span className="rpt-score-label">종합 점수</span>
                {previous ? (
                  <span>
                    <Delta value={totalDelta} />{" "}
                    <span className="muted">지난 리포트 {previous.total ?? "-"}점 대비</span>
                  </span>
                ) : (
                  <span className="muted">첫 리포트</span>
                )}
              </div>
            </div>

            <div className="rpt-actions">
              <p className="rpt-actions-title">사수 권장 조치</p>
              {actions.length ? (
                <ol>
                  {actions.map((action) => (
                    <li key={action.key}>{action.text}</li>
                  ))}
                </ol>
              ) : (
                <p className="muted">지금 따로 챙길 항목은 없습니다.</p>
              )}
              {strength && (
                <p className="rpt-strength">
                  <b>잘하고 있는 점</b> {strength.strength}
                </p>
              )}
            </div>
          </div>

          <div className="rpt-radar">
            <RadarChart axes={radarAxes} max={100} unit="점" />
          </div>
        </div>
      </section>

      <section className="rpt-sec">
        <h5 className="rpt-sec-title">
          <span>02</span>지표별 분석
        </h5>

        {SCORE_AXES.map((axis) => {
          const value = current.axes[axis.key];
          const prev = previous?.axes[axis.key];
          const delta = value !== null && prev !== null && prev !== undefined ? value - prev : null;
          const status = statusOf(value);
          const summary = summaryOf(axis.key);
          return (
            <div className="metric" key={axis.key}>
              <div className="metric-side">
                <div className="metric-name">
                  <b>{axis.label}</b>
                  <span className={`chip chip-${status}`}>{STATUS_LABEL[status]}</span>
                </div>
                <p className="metric-score">
                  {value ?? "-"}
                  <small>점</small>
                  {previous && <Delta value={delta} />}
                </p>
                <p className="metric-meaning">{axis.meaning}</p>
                <p className="metric-basis">{current.basis[axis.key]}</p>
                <p className="metric-formula">{axis.formula}</p>
              </div>
              <div className="metric-body">
                <MetricEvidence
                  axisKey={axis.key}
                  report={report}
                  previousReport={previousReport}
                  chapters={chapters}
                  checklist={checklist}
                  chatTimes={chatTimes}
                  chapterTitleOf={chapterTitleOf}
                />
                {summary && <p className="metric-summary">{summary}</p>}
              </div>
            </div>
          );
        })}
      </section>

      <details className="rpt-foot">
        <summary>산정 기준 안내</summary>
        <p>
          지표 점수는 이 리포트의 질문 기록과 체크리스트로 계산한 0~100점이고, 60점 미만을 주의로
          표시합니다. 종합 점수는 계산할 수 있는 지표의 평균이며 데이터가 없는 지표는 빠집니다.
          배정 후 2주가 안 됐으면 질문 깊이는 권장 조치에 넣지 않습니다 — 초반엔 사실 확인 질문이
          많은 게 정상이기 때문입니다. 체크리스트에는 생성 시각이 없어 분석 기간 이후 추가된 항목도
          진행도의 전체 항목 수에 들어갑니다. 점수는 적응 상태를 살피기 위한 참고 지표이며 평가
          용도가 아닙니다.
        </p>
      </details>
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
  // 날짜별 질문 흐름 그래프용. 질문 본문은 쓰지 않고 시각만 뽑아둔다.
  const [chatTimes, setChatTimes] = useState([]);
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
    getChatLogs(newcomerId)
      .then(({ data }) => {
        if (cancelled) return;
        setChatTimes((data || []).map((log) => parseServerDate(log.created_at)).filter(Boolean));
      })
      .catch(() => !cancelled && setChatTimes([]));
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
          {!selectedReport && (
            <div className="banner banner-warn">
              이 화면은 사수에게만 보입니다. 신입 화면에는 리포트가 노출되지 않습니다.
            </div>
          )}

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
              chatTimes={chatTimes}
              assignedAt={assignment?.assigned_at}
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
