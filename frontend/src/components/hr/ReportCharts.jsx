/**
 * 리포트 시각화 (사수 전용).
 *
 * 차트 라이브러리를 넣지 않고 SVG로 직접 그린다 — 도넛 하나와 레이더 하나를 위해
 * 의존성을 추가하면 번들만 커지고, 통합 테스트를 앞두고 새 패키지를 넣을 이유가 없다.
 *
 * 색은 눈대중이 아니라 검증기로 고른 순서다. 인접 색 사이 색각 이상 구분(deutan ΔE)이
 * 기준 미만이면 못 쓰는데, 아래 순서는 최악 인접쌍이 ΔE 14.1로 통과한다.
 * 순서를 바꾸거나 색을 갈아끼울 때는 반드시 다시 검증할 것.
 */

// 카테고리 색 — 항목 수에 따라 앞에서부터 순서대로 쓴다. 절대 순환시키지 않는다.
export const CHART_COLORS = [
  "#2f6feb",
  "#d1394a",
  "#0e8ea3",
  "#b8760a",
  "#7b4fc9",
  "#1f8a5b",
];

const GRID = "#e3e6ea";
const BASELINE = "#949ca6"; // 지난 리포트(기준선) — 계열색이 아니라 참조선이라 회색

/* ── 레이더 ──────────────────────────────────────────────────────
   질문 유형 4축의 프로필을 한눈에 본다. 지난 리포트를 점선으로 겹쳐 그려서
   "무엇이 늘고 무엇이 줄었는지"가 카드 하나에서 읽히게 한다. */

// 5축(오각형)까지 라벨이 뷰박스 안에 들어가도록 잡은 크기. 축 수나 라벨을 바꾸면 기하를 다시 확인할 것.
const RADAR = { w: 360, h: 256, cx: 180, cy: 132, r: 80, labelR: 104 };

function pointAt(index, count, ratio) {
  const angle = (-90 + (360 / count) * index) * (Math.PI / 180);
  return [
    RADAR.cx + RADAR.r * ratio * Math.cos(angle),
    RADAR.cy + RADAR.r * ratio * Math.sin(angle),
  ];
}

function labelAt(index, count) {
  const angle = (-90 + (360 / count) * index) * (Math.PI / 180);
  const x = RADAR.cx + RADAR.labelR * Math.cos(angle);
  const y = RADAR.cy + RADAR.labelR * Math.sin(angle);
  const cos = Math.cos(angle);
  // 축이 위/아래에 가까우면 가운데 정렬, 좌우면 바깥쪽으로 밀어낸다.
  const anchor = Math.abs(cos) < 0.3 ? "middle" : cos > 0 ? "start" : "end";
  return { x, y, anchor };
}

export function RadarChart({ axes, previousLabel, max: fixedMax, unit = "건" }) {
  const count = axes.length;
  const hasPrevious = axes.some((a) => a.previous !== undefined && a.previous !== null);

  // 두 시리즈가 같은 축척을 쓰게 최대값을 함께 잡는다 — 따로 잡으면 비교가 거짓이 된다.
  const peak = axes.reduce(
    (m, a) => Math.max(m, a.value || 0, hasPrevious ? a.previous || 0 : 0),
    0,
  );
  // 점수처럼 척도가 정해진 값은 고정 최대값을 쓴다 — 데이터에 따라 축척이 바뀌면 모양 비교가 거짓이 된다.
  const max = fixedMax || Math.max(1, peak);

  const toPath = (pick) =>
    axes
      .map((axis, i) => {
        const [x, y] = pointAt(i, count, (pick(axis) || 0) / max);
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ") + " Z";

  return (
    <div className="chart chart-radar">
      <svg viewBox={`0 0 ${RADAR.w} ${RADAR.h}`} role="img" aria-label="지표별 점수">
        {/* 눈금 고리 — 가장 바깥이 최대값이다 */}
        {[0.25, 0.5, 0.75, 1].map((ratio) => (
          <polygon
            key={ratio}
            points={axes
              .map((_, i) => pointAt(i, count, ratio).map((n) => n.toFixed(1)).join(","))
              .join(" ")}
            fill="none"
            stroke={GRID}
            strokeWidth="1"
          />
        ))}
        {axes.map((_, i) => {
          const [x, y] = pointAt(i, count, 1);
          return (
            <line
              key={i}
              x1={RADAR.cx}
              y1={RADAR.cy}
              x2={x.toFixed(1)}
              y2={y.toFixed(1)}
              stroke={GRID}
              strokeWidth="1"
            />
          );
        })}

        {hasPrevious && (
          <path
            d={toPath((a) => a.previous)}
            fill="none"
            stroke={BASELINE}
            strokeWidth="2"
            strokeDasharray="4 3"
          />
        )}

        <path
          d={toPath((a) => a.value)}
          fill={CHART_COLORS[0]}
          fillOpacity="0.16"
          stroke={CHART_COLORS[0]}
          strokeWidth="2"
          strokeLinejoin="round"
        />
        {axes.map((axis, i) => {
          const [x, y] = pointAt(i, count, (axis.value || 0) / max);
          return (
            <circle
              key={axis.label}
              cx={x.toFixed(1)}
              cy={y.toFixed(1)}
              r="4.5"
              fill={CHART_COLORS[0]}
              stroke="#fff"
              strokeWidth="2"
            >
              <title>{`${axis.label} ${axis.value || 0}${unit}`}</title>
            </circle>
          );
        })}

        {/* 축 이름과 값을 함께 적어서 색만으로 읽지 않게 한다 */}
        {axes.map((axis, i) => {
          const { x, y, anchor } = labelAt(i, count);
          return (
            <text
              key={axis.label}
              x={x.toFixed(1)}
              y={y.toFixed(1)}
              textAnchor={anchor}
              dominantBaseline="middle"
              className="chart-axis"
            >
              {axis.label}
              <tspan className="chart-axis-value" dx="4">
                {axis.value || 0}
              </tspan>
            </text>
          );
        })}
      </svg>

      <div className="chart-legend">
        <span>
          <i style={{ background: CHART_COLORS[0] }} />
          이번 리포트
        </span>
        {hasPrevious && (
          <span>
            <i className="dashed" style={{ borderColor: BASELINE }} />
            {previousLabel || "지난 리포트"}
          </span>
        )}
        <span className="chart-scale">바깥 고리 = {max}{unit}</span>
      </div>
    </div>
  );
}

/* ── 도넛 ────────────────────────────────────────────────────────
   업무별 질문이 어디에 몰렸는지를 비중으로 본다. */

const DONUT = { size: 150, cx: 75, cy: 75, r: 56, width: 20 };
const CIRCUMFERENCE = 2 * Math.PI * DONUT.r;
const MAX_SLICES = 5; // 이보다 많으면 나머지를 "기타"로 묶는다 — 색을 새로 만들지 않는다

export function DonutChart({ entries, unit = "건" }) {
  const sorted = [...entries].sort((a, b) => b.value - a.value);
  const slices =
    sorted.length > MAX_SLICES
      ? [
          ...sorted.slice(0, MAX_SLICES),
          {
            label: `기타 ${sorted.length - MAX_SLICES}개`,
            value: sorted.slice(MAX_SLICES).reduce((sum, s) => sum + s.value, 0),
          },
        ]
      : sorted;

  const total = slices.reduce((sum, s) => sum + s.value, 0);
  if (total === 0) {
    return <div className="empty" style={{ padding: 20 }}>기간 내 기록 없음</div>;
  }

  let offset = 0;
  const drawn = slices.map((slice, i) => {
    const length = (slice.value / total) * CIRCUMFERENCE;
    const seg = {
      ...slice,
      color: i < MAX_SLICES ? CHART_COLORS[i] : BASELINE,
      // 조각 사이 2px을 비워서 인접한 색이 맞닿지 않게 한다
      dash: `${Math.max(0, length - 2)} ${CIRCUMFERENCE - Math.max(0, length - 2)}`,
      offset: -offset,
      percent: Math.round((slice.value / total) * 100),
    };
    offset += length;
    return seg;
  });

  return (
    <div className="chart chart-donut">
      <svg
        viewBox={`0 0 ${DONUT.size} ${DONUT.size}`}
        role="img"
        aria-label="업무별 질문 비중"
      >
        <circle
          cx={DONUT.cx}
          cy={DONUT.cy}
          r={DONUT.r}
          fill="none"
          stroke={GRID}
          strokeWidth={DONUT.width}
        />
        <g transform={`rotate(-90 ${DONUT.cx} ${DONUT.cy})`}>
          {drawn.map((seg) => (
            <circle
              key={seg.label}
              cx={DONUT.cx}
              cy={DONUT.cy}
              r={DONUT.r}
              fill="none"
              stroke={seg.color}
              strokeWidth={DONUT.width}
              strokeDasharray={seg.dash}
              strokeDashoffset={seg.offset}
            >
              <title>{`${seg.label} ${seg.value}${unit} (${seg.percent}%)`}</title>
            </circle>
          ))}
        </g>
        <text x={DONUT.cx} y={DONUT.cy - 4} textAnchor="middle" className="chart-center-value">
          {total}
        </text>
        <text x={DONUT.cx} y={DONUT.cy + 14} textAnchor="middle" className="chart-center-unit">
          총 {unit}
        </text>
      </svg>

      <ul className="chart-legend-list">
        {drawn.map((seg) => (
          <li key={seg.label}>
            <i style={{ background: seg.color }} />
            <span className="name" title={seg.label}>
              {seg.label}
            </span>
            <span className="value">
              {seg.value}
              {unit}
            </span>
            <span className="pct">{seg.percent}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ── 질문 유형 비율 한 줄 막대 ───────────────────────────────────
   위쪽 오각형과 성격이 겹치지 않게, 질문 깊이 근거는 "비율 한 줄"로 보여준다.
   막대 하나에 유형 네 개를 이어 붙이고 건수는 범례에 적는다. */

export function ShareBar({ entries }) {
  const total = entries.reduce((sum, e) => sum + e.value, 0);
  if (!total) return <div className="empty" style={{ padding: 16 }}>기간 내 질문 없음</div>;

  return (
    <div className="share">
      <div className="share-bar">
        {entries.map((e, i) =>
          e.value ? (
            <i
              key={e.label}
              style={{ width: `${(e.value / total) * 100}%`, background: CHART_COLORS[i] }}
              title={`${e.label} ${e.value}건`}
            />
          ) : null,
        )}
      </div>
      <ul className="chart-legend-list share-legend">
        {entries.map((e, i) => (
          <li key={e.label}>
            <i style={{ background: CHART_COLORS[i] }} />
            <span className="name">{e.label}</span>
            <span className="value">{e.value}건</span>
            <span className="pct">{Math.round((e.value / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ── 날짜별 활동 달력 ─────────────────────────────────────────────
   "손을 놓지 않고 붙어 있는가"는 막대 높이보다 "어느 날에 들어왔나"가 답이다. 그래서 막대그래프
   대신 달력으로 그린다 — 날짜가 전부 적히고, 활동이 없는 날이 빈칸으로 남아 조용해진 구간이
   바로 보인다. 칸 색은 그날 질문 수, 오른쪽 위 점은 그날 체크리스트를 완료했다는 표시다. */

const DAY = 86400000;
const WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];
// 배정한 지 오래된 신입은 기간이 길어 달력이 끝없이 늘어난다. 끊긴 구간은 최근 쪽에서 보이므로
// 뒤에서부터 이만큼만 그리고, 잘렸다는 사실을 캡션에 적는다.
const MAX_WEEKS = 8;

function localMidnight(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d;
}

/** 월요일 시작으로 맞춘 요일 번호 (월 0 … 일 6) */
const weekdayIndex = (date) => (date.getDay() + 6) % 7;

export function ActivityCalendar({ questionTimes, doneTimes, start, end }) {
  if (!start || !end) return null;

  const first = localMidnight(start);
  const last = localMidnight(end);
  const key = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

  const questions = new Map();
  const dones = new Map();
  const tally = (map, times) =>
    (times || []).forEach((t) => {
      const day = localMidnight(t);
      if (day < first || day > last) return;
      map.set(key(day), (map.get(key(day)) || 0) + 1);
    });
  tally(questions, questionTimes);
  tally(dones, doneTimes);

  // 첫 주의 월요일부터 마지막 주의 일요일까지 채운다 — 요일 열이 어긋나면 달력으로 안 읽힌다.
  const gridStart = new Date(first.getTime() - weekdayIndex(first) * DAY);
  const gridEnd = new Date(last.getTime() + (6 - weekdayIndex(last)) * DAY);
  const allWeeks = [];
  for (let cursor = gridStart; cursor <= gridEnd; cursor = new Date(cursor.getTime() + 7 * DAY)) {
    allWeeks.push(
      Array.from({ length: 7 }, (_, i) => {
        const date = new Date(cursor.getTime() + i * DAY);
        const inPeriod = date >= first && date <= last;
        return {
          date,
          inPeriod,
          questions: inPeriod ? questions.get(key(date)) || 0 : 0,
          done: inPeriod ? dones.get(key(date)) || 0 : 0,
        };
      }),
    );
  }
  const truncated = allWeeks.length > MAX_WEEKS;
  const weeks = truncated ? allWeeks.slice(-MAX_WEEKS) : allWeeks;
  const shownFrom = weeks[0].find((cell) => cell.inPeriod)?.date || first;

  const level = (count) => Math.min(count, 4); // 1,2,3,4+ 네 단계
  const md = (d) => `${d.getMonth() + 1}/${d.getDate()}`;
  const ymd = (d) => `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일`;
  // 달이 바뀌는 칸(매월 1일과 기간 첫날)은 "9/1"처럼 월을 같이 적어 어느 달인지 알 수 있게 한다.
  const cellLabel = (date) =>
    date.getDate() === 1 || date.getTime() === first.getTime() ? md(date) : `${date.getDate()}`;

  return (
    <div className="cal">
      <p className="cal-caption">
        {`${ymd(shownFrom)} ~ ${ymd(last)}`}
        {truncated && <span className="cal-caption-note">최근 {MAX_WEEKS}주만 표시</span>}
      </p>
      <div className="cal-grid">
        {WEEKDAY_LABELS.map((label) => (
          <span className="cal-head" key={label}>
            {label}
          </span>
        ))}
        {weeks.flat().map((cell) => {
          const weekend = weekdayIndex(cell.date) >= 5;
          const classes = ["cal-cell"];
          if (!cell.inPeriod) classes.push("out");
          else {
            if (weekend) classes.push("weekend");
            if (cell.questions) classes.push(`lv${level(cell.questions)}`);
            if (cell.done) classes.push("done");
          }
          const title = cell.inPeriod
            ? `${md(cell.date)} 질문 ${cell.questions}건${cell.done ? ` · 체크리스트 완료 ${cell.done}개` : ""}`
            : "";
          return (
            <span className={classes.join(" ")} key={cell.date.getTime()} title={title}>
              <b>{cellLabel(cell.date)}</b>
              {cell.inPeriod && cell.questions > 0 && <i className="cal-num">{cell.questions}</i>}
            </span>
          );
        })}
      </div>
      <div className="chart-legend cal-legend">
        <span>
          <i className="cal-swatch lv0" /> 활동 없음
        </span>
        <span>
          <i className="cal-swatch lv1" /> 1건
        </span>
        <span>
          <i className="cal-swatch lv2" /> 2건
        </span>
        <span>
          <i className="cal-swatch lv3" /> 3건
        </span>
        <span>
          <i className="cal-swatch lv4" /> 4건 이상
        </span>
        <span>
          <i className="cal-swatch check">✓</i> 체크리스트 완료한 날
        </span>
      </div>
    </div>
  );
}
