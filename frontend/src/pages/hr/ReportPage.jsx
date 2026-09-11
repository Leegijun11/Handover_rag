import { useCallback, useEffect, useState } from "react";

import { getCurrentUser } from "../../api/session";
import { formatDate, formatDateTime, parseServerDate, toServerDate } from "../../api/datetime";
import { getChapters } from "../../services/router/document";
import {
  generateReport,
  getLatestReport,
  getReportHistory,
} from "../../services/router/report";
import NewcomerPicker from "../../components/hr/NewcomerPicker";
import Button from "../../components/common/Button";

/**
 * 적응도 리포트 열람 (guidelines 3-6, 4-3). 사수 전용 — 신입 화면에는 노출하지 않는다.
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

/**
 * 값이 가장 큰 항목이 100%가 되는 가로 막대.
 *
 * 라벨을 막대 왼쪽에 두지 않고 위에 올린 이유: 업무 제목이 길이가 제각각이라
 * 옆에 두면 좁은 고정폭에서 잘리거나, 어떤 줄만 두 줄이 되어 높이가 들쭉날쭉해진다.
 * 위에 올리면 제목이 카드 폭을 다 쓰고 모든 줄의 구조가 같아진다.
 */
function Bars({ entries }) {
  const max = entries.reduce((m, [, value]) => Math.max(m, value), 0);
  if (!entries.length || max === 0) {
    return <div className="empty" style={{ padding: 20 }}>기간 내 기록 없음</div>;
  }
  return (
    <div className="bars">
      {entries.map(([label, value]) => (
        <div className="bar-row" key={label}>
          <div className="bar-head">
            <span className="bar-label" title={label}>{label}</span>
            <span className="num">{value}</span>
          </div>
          <span className="bar">
            <i style={{ width: `${Math.round((value / max) * 100)}%` }} />
          </span>
        </div>
      ))}
    </div>
  );
}

function SignalBody({ section, chapterTitleOf }) {
  const data = section.data || {};

  if (section.signal_type === "growth_curve") {
    const counts = data.counts || {};
    const entries = Object.keys(QUESTION_TYPE_LABEL)
      .filter((key) => counts[key] !== undefined)
      .map((key) => [QUESTION_TYPE_LABEL[key], counts[key]]);
    return <Bars entries={entries} />;
  }

  if (section.signal_type === "chapter_heatmap") {
    const counts = data.counts || {};
    const entries = Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([chapterId, value]) => [chapterTitleOf(chapterId), value]);
    return <Bars entries={entries} />;
  }

  if (section.signal_type === "gap_task") {
    const gaps = data.gap_items || [];
    if (!gaps.length) {
      return <div className="empty" style={{ padding: 20 }}>불일치가 감지된 항목 없음</div>;
    }
    return (
      <ul className="check-list">
        {gaps.map((gap, index) => (
          <li key={`${gap.title}-${index}`}>
            <div className="body">
              <div className="title">{gap.title}</div>
              <div className="meta">완료 체크 후 질문 {gap.question_count_after_complete}건</div>
            </div>
            <span className="badge badge-warn">{gap.question_count_after_complete}</span>
          </li>
        ))}
      </ul>
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
    <div className="stat-row" style={{ marginTop: 16 }}>
      <div className="stat">
        <div className="n">{data.first_half_questions}</div>
        <div className="k">전반부 질문</div>
      </div>
      <div className="stat">
        <div className="n">{data.second_half_questions}</div>
        <div className="k">후반부 질문</div>
      </div>
      <div className="stat">
        <div className="n" style={{ color: data.dropped_sharply ? "var(--warn)" : "var(--success)" }}>
          {data.dropped_sharply ? "감지" : "정상"}
        </div>
        <div className="k">급감 여부</div>
      </div>
    </div>
  );
}

function ReportPage() {
  const mentor = getCurrentUser();

  const [assignment, setAssignment] = useState(null);
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState([]);
  const [chapters, setChapters] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const newcomerId = assignment?.newcomer_id;
  const documentId = assignment?.document_id;

  const load = useCallback(async () => {
    if (!newcomerId) return;
    setLoading(true);
    setError("");
    setReport(null);
    setHistory([]);
    try {
      const { data } = await getLatestReport(newcomerId);
      setReport(data);
    } catch (err) {
      // 404는 "아직 만든 적 없음"이라 에러가 아니다.
      if (err.response?.status !== 404) {
        setError(err.userMessage || "리포트를 불러오지 못했습니다");
      }
    }
    try {
      const { data } = await getReportHistory(newcomerId);
      setHistory(data || []);
    } catch {
      setHistory([]);
    }
    setLoading(false);
  }, [newcomerId]);

  useEffect(() => {
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

  const generatedAt = report ? parseServerDate(report.generated_at) : null;
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
      const previousEnd = report ? parseServerDate(report.period_end) : null;
      const assignedAt = parseServerDate(assignment?.assigned_at);
      const start = previousEnd || assignedAt || new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);

      await generateReport(newcomerId, toServerDate(start), periodEnd);
      await load();
      setNow(Date.now());
    } catch (err) {
      setError(err.userMessage || "리포트를 만들지 못했습니다");
      if (err.response?.status === 429) setNow(Date.now());
    } finally {
      setGenerating(false);
    }
  }

  const sections = report ? sortSections(report.sections) : [];

  return (
    <>
      <h3 className="page-title">적응도 리포트</h3>
      <p className="page-desc">담당 신입의 질문·체크리스트 기록에서 뽑은 적응 신호입니다.</p>

      <NewcomerPicker mentorId={mentor.user_id} value={assignment} onChange={setAssignment} />

      {assignment && (
        <>
          <div className="banner banner-warn">
            이 화면은 사수에게만 보입니다. 신입 화면에는 리포트가 노출되지 않습니다.
          </div>

          {error && <div className="banner banner-error">{error}</div>}

          <div className="report-head">
            <div>
              {report ? (
                <p className="page-desc" style={{ margin: 0 }}>
                  {formatDate(report.period_start)} ~ {formatDate(report.period_end)} · 생성{" "}
                  {formatDateTime(report.generated_at)}
                </p>
              ) : (
                <p className="page-desc" style={{ margin: 0 }}>
                  아직 생성된 리포트가 없습니다.
                </p>
              )}
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
                    : report
                      ? "지금 다시 생성"
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
              리포트는 5분에 한 번만 만들 수 있습니다. 방금 만든 결과를 보고 계십니다.
            </div>
          )}

          {loading ? (
            <div className="empty">불러오는 중…</div>
          ) : !report ? (
            <div className="empty">
              질문과 체크리스트가 어느 정도 쌓인 뒤에 만들면 더 정확합니다.
            </div>
          ) : (
            <>
              <div className="signal-grid">
                {sections.map((section) => (
                  <div className="card signal" key={section.signal_type}>
                    <h4>{SIGNAL_TITLE[section.signal_type] || section.signal_type}</h4>
                    <div className="sig-key">{section.signal_type}</div>
                    <p className="summary">{section.summary}</p>
                    <SignalBody section={section} chapterTitleOf={chapterTitleOf} />
                  </div>
                ))}
              </div>

              {history.length > 1 && (
                <div className="card" style={{ marginTop: 16 }}>
                  <p className="card-title">생성 이력</p>
                  <table>
                    <thead>
                      <tr>
                        <th>생성 시각</th>
                        <th>기간</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {history.map((row) => (
                        <tr key={row.report_id}>
                          <td>{formatDateTime(row.generated_at)}</td>
                          <td>
                            {formatDate(row.period_start)} ~ {formatDate(row.period_end)}
                          </td>
                          <td style={{ textAlign: "right" }}>
                            {row.report_id === report.report_id ? (
                              <span className="hint">보는 중</span>
                            ) : (
                              // 히스토리 응답에 sections가 통째로 들어 있어서 추가 호출이 필요 없다.
                              <Button size="sm" onClick={() => setReport(row)}>
                                보기
                              </Button>
                            )}
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
