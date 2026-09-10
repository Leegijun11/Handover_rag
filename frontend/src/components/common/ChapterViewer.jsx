import { useEffect, useMemo, useRef, useState } from "react";

import Button from "./Button";

/**
 * 인수인계서 본문 뷰어 — 출처 칩을 누르면 열린다.
 *
 * 두 가지를 한다.
 *  1. 배정된 문서의 업무 목록을 왼쪽에 두고 본문을 직접 오갈 수 있게 한다.
 *  2. 답변이 어느 문단에서 나왔는지 짚어서 하이라이트하고 그 위치로 스크롤한다.
 *
 * 2번을 프론트에서 계산하는 이유: /chat/ask 응답이 주는 건 source_chapter_id뿐이고,
 * 실제 근거가 된 청크 텍스트는 ChromaDB 안에만 있어서 어떤 API로도 나오지 않는다.
 * 그래서 "답변 문장이 이 문단을 얼마나 덮고 있는가"를 글자 2-gram으로 재서 추정한다.
 * 서버가 근거 텍스트를 함께 주게 되면(조장님 확인 대기 중) 이 추정은 지우고
 * 정확한 위치를 그대로 쓰면 된다.
 */

// 문단이 답변에 얼마나 덮였는지의 하한. 이보다 낮으면 하이라이트하지 않는다 —
// 엉뚱한 문단을 짚는 것보다 아무 데도 안 짚는 편이 낫다.
const MATCH_THRESHOLD = 0.34;

/** 한국어는 띄어쓰기로 자르면 잘 안 맞아서 글자 2-gram을 쓴다. */
function bigrams(text) {
  const flat = text.replace(/\s+/g, "");
  const set = new Set();
  for (let i = 0; i < flat.length - 1; i += 1) set.add(flat.slice(i, i + 2));
  return set;
}

/** 문단의 2-gram 중 답변에도 나타나는 비율. 답변이 문단을 요약·재작성해도 어느 정도 잡힌다. */
function coverage(paragraph, answer) {
  const source = bigrams(paragraph);
  if (source.size === 0) return 0;
  const target = bigrams(answer);
  let hit = 0;
  source.forEach((gram) => {
    if (target.has(gram)) hit += 1;
  });
  return hit / source.size;
}

function ChapterViewer({ chapters, chapterId, answer, onClose }) {
  const [activeId, setActiveId] = useState(chapterId);
  const markRef = useRef(null);
  const bodyRef = useRef(null);

  const active = chapters.find((c) => c.chapter_id === activeId) || chapters[0] || null;

  // 답변이 나온 업무를 보고 있을 때만 하이라이트한다. 다른 업무로 넘어가면 그냥 본문이다.
  const paragraphs = useMemo(() => {
    if (!active) return [];
    const blocks = active.content.split(/\n{2,}/).filter((p) => p.trim());
    if (!answer || active.chapter_id !== chapterId) {
      return blocks.map((text) => ({ text, matched: false }));
    }
    const scored = blocks.map((text) => ({ text, score: coverage(text, answer) }));
    const best = scored.reduce((max, p) => Math.max(max, p.score), 0);
    if (best < MATCH_THRESHOLD) {
      return blocks.map((text) => ({ text, matched: false }));
    }
    // 최고점에 가까운 문단은 함께 짚는다 — 답변이 두 문단에 걸쳐 나오는 경우가 있다.
    return scored.map((p) => ({ text: p.text, matched: p.score >= Math.max(MATCH_THRESHOLD, best * 0.9) }));
  }, [active, answer, chapterId]);

  const hasMatch = paragraphs.some((p) => p.matched);

  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // 하이라이트된 문단이 화면 밖에 있으면 거기로 옮겨준다. 긴 업무일수록 이게 없으면
  // 본문만 열리고 "그래서 어디?"가 된다.
  useEffect(() => {
    if (markRef.current && bodyRef.current) {
      markRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    } else if (bodyRef.current) {
      bodyRef.current.scrollTop = 0;
    }
  }, [activeId, hasMatch]);

  if (!active) return null;

  let firstMatchSeen = false;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="chapter-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h4 id="chapter-title">인수인계서</h4>
          <Button size="sm" autoFocus onClick={onClose}>
            닫기
          </Button>
        </div>

        <div className="viewer">
          <nav className="viewer-nav" aria-label="업무 목록">
            {chapters.map((chapter) => (
              <button
                type="button"
                key={chapter.chapter_id}
                className={chapter.chapter_id === activeId ? "active" : undefined}
                onClick={() => setActiveId(chapter.chapter_id)}
              >
                {chapter.title}
                {/* 답변에서 열었을 때만 출처 표시를 단다. 체크리스트에서 그냥 읽으러 온 경우엔 의미가 없다. */}
                {answer && chapter.chapter_id === chapterId && (
                  <span className="dot" aria-label="답변 출처" />
                )}
              </button>
            ))}
          </nav>

          <div className="viewer-body" ref={bodyRef}>
            <h5>{active.title}</h5>
            {active.chapter_id === chapterId && (
              <p className="viewer-note">
                {hasMatch
                  ? "답변의 근거로 보이는 부분을 표시했습니다."
                  : "이 업무를 참고해 답변했습니다. 문단까지는 짚지 못했습니다."}
              </p>
            )}
            {paragraphs.map((paragraph, index) => {
              if (!paragraph.matched) {
                return <p key={index}>{paragraph.text}</p>;
              }
              const isFirst = !firstMatchSeen;
              firstMatchSeen = true;
              return (
                <p key={index}>
                  <mark ref={isFirst ? markRef : undefined}>{paragraph.text}</mark>
                </p>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ChapterViewer;
