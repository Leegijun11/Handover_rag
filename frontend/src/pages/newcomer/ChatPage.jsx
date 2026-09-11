import { useEffect, useMemo, useRef, useState } from "react";

import { getCurrentUser } from "../../api/session";
import { askChat, getChatLogs } from "../../services/router/chat";
import { getChecklist } from "../../services/router/checklist";
import { getChapters } from "../../services/router/document";
import { useNewcomerScope } from "../../components/common/NewcomerScope";
import ChapterViewer from "../../components/common/ChapterViewer";
import Button from "../../components/common/Button";

/**
 * 신입 챗봇 대화 (guidelines 3-3, 4-3).
 *
 * ChatLog에 answer(신설, guidelines 2-4)가 저장되므로 GET /chat/logs로 이전 대화를
 * 복원한다 — 아래 두 번째 useEffect 참고. 단, 재배정으로 sourceChapterId가 옛 문서의
 * 챕터를 가리키게 되면(guidelines 3-1) 그 메시지의 출처 칩만 사라진다 — 메시지 자체는
 * 그대로 복원된다.
 *
 * 답변 실패(answered=false) 시 문구에 "문서를 보강하겠다"는 취지를 넣지 않는다 —
 * 그 얘기는 사수 리포트에서만 다룬다 (guidelines 1-7).
 */

const MAX_QUESTION_LENGTH = 500; // guidelines 5-9 항목 2
const RATE_LIMIT_COOLDOWN_SECONDS = 60; // 사용자별 제한이 분당 10회라 1분 쉬면 풀린다
const MAX_SUGGESTIONS = 3;

function ChatPage() {
  const user = getCurrentUser();
  const newcomerId = user?.user_id;
  const { assignment, mentorName, loading: scopeLoading, error: scopeError, unassigned } =
    useNewcomerScope();
  const documentId = assignment?.document_id;

  const [chapters, setChapters] = useState([]);
  const [checklist, setChecklist] = useState([]);
  const [askedChapterIds, setAskedChapterIds] = useState(() => new Set());
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const [openSource, setOpenSource] = useState(null);
  const [copied, setCopied] = useState(false);

  const logRef = useRef(null);

  // 출처 칩에 chapter_id 대신 업무 제목을 띄우고, 본문 뷰어를 열려면 챕터 목록이 필요하다.
  // MySQL만 읽는 조회라 OpenAI 키와 무관하게 동작한다 (guidelines 3-2).
  useEffect(() => {
    if (!documentId) return undefined;
    let cancelled = false;
    getChapters(documentId)
      .then(({ data }) => {
        if (!cancelled) setChapters(data || []);
      })
      .catch(() => {
        // 실패해도 대화는 되어야 한다. 출처 칩과 제안만 빠진다.
        if (!cancelled) setChapters([]);
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  // 선제안에 쓸 재료. 둘 다 MySQL 전용 조회이고, 실패해도 화면은 그대로 돌아간다.
  useEffect(() => {
    if (!newcomerId) return undefined;
    let cancelled = false;
    getChecklist(newcomerId)
      .then(({ data }) => !cancelled && setChecklist(data || []))
      .catch(() => !cancelled && setChecklist([]));
    getChatLogs(newcomerId)
      .then(({ data }) => {
        if (cancelled) return;
        // /chat/logs는 이 신입의 전체 이력을 준다(HR 원본 로그 조회 등 다른 용도도
        // 있어서 API 자체는 안 좁힘, guidelines 3-3). 재배정 전 옛 문서 대화까지
        // 여기서 같이 복원되면 안 되므로, 지금 배정된 document_id로 화면단에서 거른다
        // (ChatLog.document_id, guidelines 2-4).
        const logs = (data || []).filter((log) => log.document_id === documentId);
        const asked = logs.map((log) => log.matched_chapter_id).filter(Boolean);
        setAskedChapterIds(new Set(asked));
        // ChatLog에 answer가 저장되므로(guidelines 2-4) 화면을 벗어났다 돌아와도
        // 대화를 복원할 수 있다. /chat/logs는 최신순으로 오므로 대화 순서로 뒤집고,
        // 로그 한 건을 질문/답변 말풍선 두 개로 편다.
        const restored = [...logs].reverse().flatMap((log) => [
          { role: "me", text: log.question },
          {
            role: "bot",
            text: log.answer,
            answered: log.answered,
            sourceChapterId: log.matched_chapter_id,
          },
        ]);
        setMessages(restored);
      })
      .catch(() => !cancelled && setAskedChapterIds(new Set()));
    return () => {
      cancelled = true;
    };
  }, [newcomerId, documentId]);

  // 새 말풍선이 붙으면 항상 맨 아래가 보이게 한다.
  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [messages, sending]);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = setInterval(() => setCooldown((n) => Math.max(0, n - 1)), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  function chapterOf(chapterId) {
    if (!chapterId) return null;
    return chapters.find((c) => c.chapter_id === chapterId) || null;
  }

  /**
   * 무엇을 물어야 할지 먼저 제안한다.
   *
   * 서버를 새로 부르지 않고, 이미 가진 세 가지(배정 문서의 업무 목록, 체크리스트,
   * 지난 질문 기록)만으로 규칙으로 고른다. LLM 호출이 없어서 비용도 지연도 없다.
   * 우선순위는 "지금 막힌 것 > 아직 안 해본 것" 순이다.
   */
  const suggestions = useMemo(() => {
    const picked = [];
    const seen = new Set();
    const add = (question, reason) => {
      if (picked.length >= MAX_SUGGESTIONS || seen.has(question)) return;
      seen.add(question);
      picked.push({ question, reason });
    };

    const lastBot = [...messages].reverse().find((m) => m.role === "bot");

    // 1) 방금 답을 못 찾았다면, 문서에 실제로 있는 업무부터 보여준다.
    //    "문서를 보강하겠다"는 말은 하지 않으면서 다음 행동을 제시하는 방법이다 (1-7).
    if (lastBot && lastBot.answered === false) {
      chapters.forEach((c) => add(`${c.title}에 대해 알려주세요`, "이 문서에 있는 업무"));
      return picked;
    }

    // 2) 아직 완료하지 않은 체크리스트 항목 중 업무가 연결된 것
    checklist
      .filter((item) => item.status !== "done" && item.chapter_id)
      .forEach((item) => {
        const chapter = chapterOf(item.chapter_id);
        if (chapter) add(`${chapter.title}은 어떻게 하나요?`, "아직 완료하지 않은 할 일");
      });

    // 3) 한 번도 질문해본 적 없는 업무
    chapters
      .filter((c) => !askedChapterIds.has(c.chapter_id))
      .forEach((c) => add(`${c.title}에 대해 알려주세요`, "아직 물어보지 않은 업무"));

    return picked;
    // chapterOf는 chapters에서 파생되므로 별도 의존성으로 넣지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, chapters, checklist, askedChapterIds]);

  async function send(text) {
    if (!text || sending || cooldown > 0) return;

    setMessages((prev) => [...prev, { role: "me", text }]);
    setQuestion("");
    setSending(true);
    setError("");

    try {
      const { data } = await askChat(newcomerId, text);
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: data.answer,
          answered: data.answered,
          sourceChapterId: data.source_chapter_id,
        },
      ]);
      // 이미 물어본 업무는 제안 목록에서 빠지게 한다.
      if (data.source_chapter_id) {
        setAskedChapterIds((prev) => new Set(prev).add(data.source_chapter_id));
      }
    } catch (err) {
      if (err.response?.status === 429) {
        setCooldown(RATE_LIMIT_COOLDOWN_SECONDS);
        setError("질문이 너무 빨랐습니다. 잠시 뒤에 다시 물어보세요.");
      } else {
        setError(err.userMessage || "답변을 받지 못했습니다");
      }
      // 방금 보낸 질문을 입력칸에 되돌려준다 — 다시 타이핑하게 만들지 않는다.
      setQuestion(text);
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    send(question.trim());
  }

  async function copyMyId() {
    try {
      await navigator.clipboard.writeText(newcomerId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // 클립보드 접근이 막힌 브라우저 — 아이디는 화면에 그대로 보이므로 직접 복사하면 된다.
      setCopied(false);
    }
  }

  if (scopeLoading) {
    return <div className="empty">불러오는 중…</div>;
  }

  if (scopeError) {
    return <div className="banner banner-error">{scopeError}</div>;
  }

  // 배정 전 신입이 처음 보게 되는 화면이다. 사수가 배정하려면 이 사람의 user_id가
  // 필요한데 그걸 알려주는 화면이 따로 없어서, 여기서 바로 복사할 수 있게 둔다.
  if (unassigned) {
    return (
      <>
        <h3 className="page-title">챗봇에게 물어보기</h3>
        <p className="page-desc">배정된 인수인계서가 있어야 질문할 수 있습니다.</p>
        <div className="empty">
          아직 배정된 인수인계서가 없습니다.
          <br />
          사수님께 아래 코드를 알려주시면 문서를 배정받을 수 있습니다.
          <div className="id-chip">
            <code>{newcomerId}</code>
            <Button size="sm" onClick={copyMyId}>
              {copied ? "복사했습니다" : "복사"}
            </Button>
          </div>
        </div>
      </>
    );
  }

  const canSend = question.trim().length > 0 && !sending && cooldown === 0;
  // 대화 안의 카드라서 타이핑 중에 사라지게 하지 않는다 — 화면이 덜컥거린다.
  // 답변을 기다리는 동안에만 감춘다.
  const showSuggestions = suggestions.length > 0 && !sending;

  return (
    <>
      <div className="chat">
        <div className="chat-bar">
          <span className="chat-bar-title">
            배정된 인수인계서
            {chapters.length > 0 ? ` · 업무 ${chapters.length}개` : ""}
          </span>
          <Button
            size="sm"
            disabled={!chapters.length}
            onClick={() => setOpenSource({ chapterId: chapters[0]?.chapter_id, answer: null })}
          >
            인수인계서 보기
          </Button>
        </div>

        <div className="chat-log" ref={logRef}>
          <div className="msg msg-bot">
            <div className="bubble">
              안녕하세요. {mentorName ? `${mentorName} 님이 ` : ""}배정한 인수인계서를 읽었습니다.
              {chapters.length > 0 ? ` 업무 ${chapters.length}개가 담겨 있습니다.` : ""}
              <br />이 문서에 적힌 내용만 답할 수 있습니다. 궁금한 걸 물어보세요.
            </div>
          </div>

          {messages.map((message, index) => {
            if (message.role === "me") {
              return (
                <div className="msg msg-me" key={index}>
                  <div className="bubble">{message.text}</div>
                </div>
              );
            }
            const chapter = chapterOf(message.sourceChapterId);
            return (
              <div className="msg msg-bot" key={index}>
                <div className="bubble">
                  {message.text}
                  {/* 답변에 성공했고 그 업무를 찾을 수 있을 때만 칩을 그린다.
                      재배정으로 옛 문서의 챕터를 가리키는 경우엔 칩이 사라진다. */}
                  {message.answered && chapter && (
                    <>
                      <br />
                      <button
                        type="button"
                        className="source"
                        onClick={() =>
                          setOpenSource({ chapterId: chapter.chapter_id, answer: message.text })
                        }
                      >
                        {chapter.title}
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}

          {sending && (
            <div className="msg msg-bot">
              <div className="bubble">
                <span className="typing" aria-label="답변을 작성하는 중입니다">
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            </div>
          )}

          {/* 제안은 입력창 위 칩이 아니라 대화 흐름 안의 카드로 둔다.
              방금 한 말에 이어지는 다음 선택지로 읽히고, 스크롤에도 같이 따라간다. */}
          {showSuggestions && (
            <div className="msg msg-bot msg-suggest">
              <span className="suggests-label">이런 걸 물어보실 수 있어요</span>
              <div className="suggest-cards">
                {suggestions.map((item) => (
                  <button
                    type="button"
                    className="suggest-card"
                    key={item.question}
                    onClick={() => send(item.question)}
                  >
                    <span className="reason">{item.reason}</span>
                    <span className="q">{item.question}</span>
                    <span className="go" aria-hidden="true">→</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="chat-alert">
            <div className="banner banner-warn">
              {error}
              {cooldown > 0 ? ` (${cooldown}초)` : ""}
            </div>
          </div>
        )}

        <form className="chat-input" onSubmit={handleSubmit}>
          <input
            type="text"
            id="chat-question"
            value={question}
            maxLength={MAX_QUESTION_LENGTH}
            placeholder={sending ? "답변을 기다리는 중입니다" : "예: 정산 마감일이 언제예요?"}
            disabled={sending || cooldown > 0}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <span
            className={`counter${MAX_QUESTION_LENGTH - question.length <= 50 ? " counter-warn" : ""}`}
          >
            {question.length} / {MAX_QUESTION_LENGTH}
          </span>
          <Button type="submit" variant="primary" disabled={!canSend}>
            {sending ? "보내는 중…" : "보내기"}
          </Button>
        </form>
      </div>

      {openSource && (
        <ChapterViewer
          chapters={chapters}
          chapterId={openSource.chapterId}
          answer={openSource.answer}
          onClose={() => setOpenSource(null)}
        />
      )}
    </>
  );
}

export default ChatPage;
