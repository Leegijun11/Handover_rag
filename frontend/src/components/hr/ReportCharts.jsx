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

/* ── 날짜별 질문 흐름 ─────────────────────────────────────────────
   "질문이 끊겼는가"는 앞/뒤 절반 합계 두 숫자보다 날짜별 막대로 봐야 읽힌다.
   기간 중간에 점선을 그어서 서버가 급감 여부를 판단하는 기준선을 같이 보여준다. */

const TL = { w: 640, h: 170, left: 30, right: 10, top: 14, bottom: 26 };
const DAY = 86400000;

function localMidnight(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d;
}

export function QuestionTimeline({ times, start, end, dropped }) {
  if (!start || !end) return null;

  const firstDay = localMidnight(start);
  const days = Math.max(1, Math.round((localMidnight(end) - firstDay) / DAY) + 1);
  // 기간이 한 달을 넘으면 막대가 가늘어져 읽히지 않으므로 주 단위로 묶는다.
  const step = days > 31 ? 7 : 1;
  const buckets = Math.ceil(days / step);
  const counts = new Array(buckets).fill(0);
  times.forEach((t) => {
    const index = Math.floor((localMidnight(t) - firstDay) / DAY / step);
    if (index >= 0 && index < buckets) counts[index] += 1;
  });

  const plotW = TL.w - TL.left - TL.right;
  const plotH = TL.h - TL.top - TL.bottom;
  const slot = plotW / buckets;
  const barW = Math.max(3, Math.min(28, slot - 4));
  const max = Math.max(1, ...counts);
  const baseY = TL.top + plotH;

  const mid = new Date((start.getTime() + end.getTime()) / 2);
  const midX = TL.left + ((mid - firstDay) / (buckets * step * DAY)) * plotW;
  const md = (d) => `${d.getMonth() + 1}/${d.getDate()}`;
  const bucketDate = (i) => new Date(firstDay.getTime() + i * step * DAY);

  return (
    <div className="timeline">
      <svg viewBox={`0 0 ${TL.w} ${TL.h}`} role="img" aria-label="날짜별 질문 수">
        <line x1={TL.left} x2={TL.w - TL.right} y1={TL.top} y2={TL.top} stroke={GRID} strokeWidth="1" />
        <line x1={TL.left} x2={TL.w - TL.right} y1={baseY} y2={baseY} stroke="#cdd3da" strokeWidth="1" />
        <text x={TL.left - 6} y={TL.top} textAnchor="end" dominantBaseline="middle" className="chart-axis">
          {max}
        </text>
        <text x={TL.left - 6} y={baseY} textAnchor="end" dominantBaseline="middle" className="chart-axis">
          0
        </text>

        {counts.map((count, i) => {
          if (!count) return null;
          const h = Math.max(2, (count / max) * plotH);
          const x = TL.left + slot * i + (slot - barW) / 2;
          const afterMid = x + barW / 2 > midX;
          return (
            <rect
              key={i}
              x={x.toFixed(1)}
              y={(baseY - h).toFixed(1)}
              width={barW.toFixed(1)}
              height={h.toFixed(1)}
              rx="3"
              fill={afterMid && dropped ? CHART_COLORS[3] : CHART_COLORS[0]}
            >
              <title>{`${md(bucketDate(i))}${step > 1 ? " 주" : ""} 질문 ${count}건`}</title>
            </rect>
          );
        })}

        <line
          x1={midX.toFixed(1)}
          x2={midX.toFixed(1)}
          y1={TL.top - 4}
          y2={baseY}
          stroke={BASELINE}
          strokeWidth="1.5"
          strokeDasharray="4 3"
        />
        <text x={midX.toFixed(1)} y={TL.h - 6} textAnchor="middle" className="chart-axis">
          중간 {md(mid)}
        </text>
        <text x={TL.left} y={TL.h - 6} textAnchor="start" className="chart-axis">
          {md(start)}
        </text>
        <text x={TL.w - TL.right} y={TL.h - 6} textAnchor="end" className="chart-axis">
          {md(end)}
        </text>
      </svg>
    </div>
  );
}
