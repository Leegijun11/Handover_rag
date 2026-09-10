import { useCallback, useEffect, useMemo, useState } from "react";
import {
  deleteChecklistItem,
  draftChecklist,
  getChecklist,
  reorderChecklistItem,
  saveChecklist,
  updateChecklistItem,
} from "../../services/router/checklist";
import { getChapters } from "../../services/router/document";
import { getCurrentUser } from "../../api/session";
import { readingTaskTitle } from "../../api/handoverTemplate";
import NewcomerPicker from "../../components/hr/NewcomerPicker";
import Button from "../../components/common/Button";
import ChapterViewer from "../../components/common/ChapterViewer";
import Field from "../../components/common/Field";

function ChecklistManagePage() {
  const mentor = getCurrentUser();

  const [assignment, setAssignment] = useState(null);
  const [items, setItems] = useState([]);
  const [chapters, setChapters] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // 초안은 저장 전까지 화면에만 있는 값이다 (guidelines 3-4 — draft는 저장하지 않음).
  // AI가 만든 것과 업무별 읽기 항목 두 가지가 같은 미리보기 UI를 쓴다.
  const [draft, setDraft] = useState(null);
  const [draftKind, setDraftKind] = useState(null); // "ai" | "reading"
  const [drafting, setDrafting] = useState(false);

  // 수정 중인 항목. 모달(prompt) 대신 행을 입력칸으로 바꾼다 — 편집하려는 항목을
  // 계속 보면서 고칠 수 있고, 브라우저 모달이 화면을 막지도 않는다.
  const [editing, setEditing] = useState(null); // { itemId, title }
  const [newTitle, setNewTitle] = useState("");
  // 대분류(장)와 소분류(절)를 따로 들고, 저장할 때 더 좁은 쪽을 chapter_id로 쓴다.
  const [newTopId, setNewTopId] = useState("");
  const [newSubId, setNewSubId] = useState("");
  const [busy, setBusy] = useState(false);
  const [viewingChapterId, setViewingChapterId] = useState(null);

  const newcomerId = assignment?.newcomer_id;
  const documentId = assignment?.document_id;

  const loadItems = useCallback(async () => {
    if (!newcomerId) return;
    setLoading(true);
    setError("");
    try {
      const { data } = await getChecklist(newcomerId);
      setItems(data || []);
    } catch (err) {
      setError(err.userMessage || "체크리스트를 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  }, [newcomerId]);

  useEffect(() => {
    setDraft(null);
    setDraftKind(null);
    setNotice("");
    loadItems();
  }, [loadItems]);

  useEffect(() => {
    if (!documentId) return;
    let cancelled = false;
    // 직접 추가할 때 연결할 업무 목록. 실패해도 화면은 쓸 수 있어야 하므로 조용히 비운다
    // (업무 연결은 선택 항목이다).
    getChapters(documentId)
      .then(({ data }) => !cancelled && setChapters(data || []))
      .catch(() => !cancelled && setChapters([]));
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  /**
   * 업무의 장-절 구조를 푼다.
   *
   * DocumentChapter.parent_id가 계층을 담는 필드인데(guidelines 2), 지금 팀원 A의
   * 업로드 파이프라인은 이 값을 항상 None으로 저장한다. 그래서 실제로는 전부
   * 대분류로만 들어온다 — 그 경우 소분류 줄은 나오지 않고 한 단계로 동작한다.
   * parent_id가 채워지면 코드 변경 없이 두 단계로 늘어난다.
   */
  const outline = useMemo(() => {
    const byId = new Map(chapters.map((c) => [c.chapter_id, c]));
    // parent가 목록에 없는 챕터는 고아로 두지 않고 대분류로 취급한다.
    const isTop = (c) => !c.parent_id || !byId.has(c.parent_id);

    const tops = chapters.filter(isTop);
    const childrenOf = new Map(
      tops.map((top) => [
        top.chapter_id,
        chapters.filter((c) => !isTop(c) && c.parent_id === top.chapter_id),
      ]),
    );

    // 화면에 보여줄 번호 (1, 2 / 1-1, 1-2). chapter_id가 UUID라 순서로 매긴다.
    const numbers = new Map();
    tops.forEach((top, i) => {
      numbers.set(top.chapter_id, String(i + 1));
      (childrenOf.get(top.chapter_id) || []).forEach((sub, j) => {
        numbers.set(sub.chapter_id, `${i + 1}-${j + 1}`);
      });
    });

    return { tops, childrenOf, numbers, hasDepth: tops.length !== chapters.length };
  }, [chapters]);

  function chapterTitle(chapterId) {
    if (!chapterId) return "연결된 업무 없음";
    const chapter = chapters.find((c) => c.chapter_id === chapterId);
    if (!chapter) return chapterId;
    const number = outline.numbers.get(chapterId);
    return number ? `${number}. ${chapter.title}` : chapter.title;
  }

  const nextOrder = items.reduce((max, item) => Math.max(max, item.order ?? 0), 0) + 1;

  async function handleDraft() {
    setDrafting(true);
    setError("");
    setNotice("");
    try {
      const { data } = await draftChecklist(documentId);
      // 초안은 전부 선택된 상태로 시작한다 — 사수가 빼는 편이 하나씩 고르는 것보다 빠르다.
      setDraft(
        (data || []).map((c, i) => ({ ...c, key: `${i}-${c.title}`, checked: true, source: "ai_draft" })),
      );
      setDraftKind("ai");
    } catch (err) {
      setError(err.userMessage || "초안을 만들지 못했습니다");
    } finally {
      setDrafting(false);
    }
  }

  /**
   * 업무별로 "○○ 읽어보기" 항목을 만든다.
   *
   * 읽었는지를 따로 기록하는 테이블을 만들지 않고 체크리스트를 그대로 쓰는 이유:
   * 리포트의 gap_task 신호가 원래 "완료 체크 후에도 같은 챕터를 계속 묻는가"를 보기 때문에,
   * 읽기 항목이 체크리스트에 들어가는 순간 "읽었다는데 계속 묻는다"가 자동으로 잡힌다.
   * 스키마도 API도 건드리지 않고 신호 하나가 더 날카로워진다.
   */
  function handleReadingTasks() {
    setError("");
    setNotice("");
    const existing = new Set(items.map((item) => item.title));
    const candidates = chapters
      .map((chapter, i) => ({
        title: readingTaskTitle(chapter.title),
        chapter_id: chapter.chapter_id,
        key: `read-${i}-${chapter.chapter_id}`,
        source: "manual",
        // 이미 있는 항목은 기본으로 빼둔다 — 두 번 눌러도 중복 저장되지 않게.
        checked: !existing.has(readingTaskTitle(chapter.title)),
      }));
    setDraft(candidates);
    setDraftKind("reading");
  }

  async function handleSaveDraft() {
    const chosen = draft.filter((d) => d.checked);
    if (!chosen.length) return;
    setBusy(true);
    setError("");
    try {
      await saveChecklist(
        chosen.map((d, i) => ({
          newcomer_id: newcomerId,
          chapter_id: d.chapter_id || null,
          title: d.title,
          order: nextOrder + i,
          source: d.source || "ai_draft",
        })),
      );
      setDraft(null);
      setDraftKind(null);
      setNotice(`${chosen.length}개를 저장했습니다.`);
      await loadItems();
    } catch (err) {
      setError(err.userMessage || "저장하지 못했습니다");
    } finally {
      setBusy(false);
    }
  }

  async function handleAdd(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await saveChecklist([
        {
          newcomer_id: newcomerId,
          // 소분류까지 골랐으면 그쪽이 더 정확한 연결이다.
          chapter_id: newSubId || newTopId || null,
          title: newTitle.trim(),
          order: nextOrder,
          source: "manual",
        },
      ]);
      setNewTitle("");
      setNewTopId("");
      setNewSubId("");
      setNotice("항목을 추가했습니다.");
      await loadItems();
    } catch (err) {
      setError(err.userMessage || "추가하지 못했습니다");
    } finally {
      setBusy(false);
    }
  }

  async function handleRename(e) {
    e.preventDefault();
    const next = editing.title.trim();
    if (!next) return;
    setBusy(true);
    setError("");
    try {
      await updateChecklistItem(editing.itemId, { title: next });
      setEditing(null);
      await loadItems();
    } catch (err) {
      setError(err.userMessage || "수정하지 못했습니다");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(item) {
    setBusy(true);
    setError("");
    try {
      await deleteChecklistItem(item.item_id);
      setNotice("항목을 삭제했습니다.");
      await loadItems();
    } catch (err) {
      setError(err.userMessage || "삭제하지 못했습니다");
    } finally {
      setBusy(false);
    }
  }

  async function handleMove(index, direction) {
    const target = index + direction;
    if (target < 0 || target >= items.length) return;
    const moved = items[index];
    const swapped = items[target];
    setBusy(true);
    try {
      // 두 항목의 order를 맞바꾼다. reorder는 항목 하나의 order만 받으므로 두 번 호출한다.
      await reorderChecklistItem(moved.item_id, swapped.order);
      try {
        await reorderChecklistItem(swapped.item_id, moved.order);
      } catch (err) {
        // 첫 호출만 성공하면 두 항목의 order가 같아져서 이후 정렬이 뒤죽박죽이 된다.
        // 되돌려서 원래 순서를 지킨 뒤 실패로 처리한다.
        await reorderChecklistItem(moved.item_id, moved.order).catch(() => {});
        throw err;
      }
      await loadItems();
    } catch (err) {
      setError(err.userMessage || "순서를 바꾸지 못했습니다");
      await loadItems();
    } finally {
      setBusy(false);
    }
  }

  const draftChosen = draft?.filter((d) => d.checked).length ?? 0;
  const subChapters = newTopId ? outline.childrenOf.get(newTopId) || [] : [];

  return (
    <>
      <h3 className="page-title">체크리스트 관리</h3>
      <p className="page-desc">배정한 신입을 골라 체크리스트를 작성합니다.</p>

      <NewcomerPicker mentorId={mentor.user_id} value={assignment} onChange={setAssignment}>
        <span style={{ fontSize: 12, color: "var(--text-faint)", marginLeft: "auto" }}>
          {items.length}개 중 {items.filter((i) => i.status === "done").length}개 완료
        </span>
        {/* 어떤 업무를 항목으로 만들지 정하려면 본문을 봐야 한다. 화면을 떠나지 않고 열어본다. */}
        <Button
          size="sm"
          disabled={!chapters.length}
          onClick={() => setViewingChapterId(chapters[0].chapter_id)}
        >
          인수인계서 보기
        </Button>
      </NewcomerPicker>

      {assignment && (
        <>
          {error && <div className="banner banner-error">{error}</div>}
          {notice && <div className="banner banner-info">{notice}</div>}

          <div className="card">
            <p className="card-title">항목 만들기</p>
            <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--text-muted)" }}>
              인수인계서를 바탕으로 후보를 뽑아옵니다. 승인하기 전까지는 저장되지 않습니다.
            </p>
            <div className="actions" style={{ marginTop: 0 }}>
              <Button variant="primary" onClick={handleDraft} disabled={drafting || busy}>
                {drafting ? "초안 만드는 중…" : "AI로 할 일 뽑기"}
              </Button>
              <Button onClick={handleReadingTasks} disabled={drafting || busy || !chapters.length}>
                업무별 읽기 항목 만들기
              </Button>
            </div>
            {!chapters.length && (
              <p className="hint" style={{ marginTop: 8 }}>
                업무 목록을 불러오지 못해 읽기 항목을 만들 수 없습니다.
              </p>
            )}

            {draft && (
              <div style={{ marginTop: 16 }}>
                {draft.length === 0 ? (
                  <div className="empty">
                    {draftKind === "reading"
                      ? "인수인계서에 등록된 업무가 없습니다."
                      : "후보를 만들지 못했습니다."}
                  </div>
                ) : (
                  <>
                    <ul className="check-list">
                      {draft.map((candidate) => (
                        <li key={candidate.key}>
                          <input
                            type="checkbox"
                            checked={candidate.checked}
                            onChange={(e) =>
                              setDraft((prev) =>
                                prev.map((d) =>
                                  d.key === candidate.key
                                    ? { ...d, checked: e.target.checked }
                                    : d,
                                ),
                              )
                            }
                          />
                          <div className="body">
                            <div className="title">{candidate.title}</div>
                            <div className="meta">{chapterTitle(candidate.chapter_id)}</div>
                          </div>
                          {candidate.source === "ai_draft" ? (
                            <span className="badge badge-ai">AI 초안</span>
                          ) : (
                            <span className="badge badge-manual">읽기</span>
                          )}
                        </li>
                      ))}
                    </ul>
                    <div className="actions actions-end">
                      <Button
                        onClick={() =>
                          setDraft((prev) => prev.map((d) => ({ ...d, checked: false })))
                        }
                      >
                        모두 해제
                      </Button>
                      <Button
                        variant="primary"
                        disabled={draftChosen === 0 || busy}
                        onClick={handleSaveDraft}
                      >
                        선택한 {draftChosen}개 저장
                      </Button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          <div className="card">
            <p className="card-title">
              저장된 항목{" "}
              <span className="badge badge-manual" style={{ marginLeft: 4 }}>
                {items.length}개
              </span>
            </p>

            {loading ? (
              <div className="empty">불러오는 중…</div>
            ) : items.length === 0 ? (
              <div className="empty">아직 항목이 없습니다. 아래에서 추가하세요.</div>
            ) : (
              <ul className="check-list">
                {items.map((item, index) =>
                  editing?.itemId === item.item_id ? (
                    <li key={item.item_id}>
                      <form className="edit-row" onSubmit={handleRename}>
                        <input
                          type="text"
                          value={editing.title}
                          autoFocus
                          onChange={(e) => setEditing({ ...editing, title: e.target.value })}
                        />
                        <Button type="submit" size="sm" variant="primary" disabled={busy}>
                          저장
                        </Button>
                        <Button size="sm" disabled={busy} onClick={() => setEditing(null)}>
                          취소
                        </Button>
                      </form>
                    </li>
                  ) : (
                  <li key={item.item_id} className={item.status === "done" ? "done" : undefined}>
                    <div className="reorder">
                      <button
                        type="button"
                        disabled={index === 0 || busy}
                        onClick={() => handleMove(index, -1)}
                        aria-label="위로"
                      >
                        ▲
                      </button>
                      <button
                        type="button"
                        disabled={index === items.length - 1 || busy}
                        onClick={() => handleMove(index, 1)}
                        aria-label="아래로"
                      >
                        ▼
                      </button>
                    </div>
                    <div className="body">
                      <div className="title">{item.title}</div>
                      <div className="meta">
                        {chapterTitle(item.chapter_id)} ·{" "}
                        {item.source === "ai_draft" ? "AI 초안" : "직접 작성"}
                        {item.status === "done" ? " · 완료" : ""}
                      </div>
                    </div>
                    <Button
                      size="sm"
                      disabled={busy}
                      onClick={() => setEditing({ itemId: item.item_id, title: item.title })}
                    >
                      수정
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      disabled={busy}
                      onClick={() => handleDelete(item)}
                    >
                      삭제
                    </Button>
                  </li>
                  ),
                )}
              </ul>
            )}

            <form
              className="card"
              style={{ background: "var(--surface-2)", marginTop: 14 }}
              onSubmit={handleAdd}
            >
              <p className="card-title">직접 추가</p>

              {/* 업무(대분류)를 먼저 고르고 할 일(소분류)을 적는 2단계.
                  드롭다운이 아니라 버튼으로 편 이유는, 어떤 업무들이 있는지 자체가
                  "무엇을 시킬까"의 힌트이기 때문이다. 펼쳐놔야 눈에 들어온다. */}
              {/* 업무 선택은 두 단계로 나눈다. 대분류를 고르면 소분류 목록이 그 아래
                  절만 남게 좁혀진다. 지금은 parent_id가 채워지지 않아 소분류가 비는데,
                  그 경우 두 번째 박스는 잠긴 채로 안내만 띄운다. */}
              <div className="row-2">
                <Field label="대분류">
                  {(props) => (
                    <select
                      {...props}
                      value={newTopId}
                      onChange={(e) => {
                        setNewTopId(e.target.value);
                        setNewSubId("");
                      }}
                    >
                      <option value="">연결 안 함</option>
                      {outline.tops.map((chapter) => (
                        <option key={chapter.chapter_id} value={chapter.chapter_id}>
                          {outline.numbers.get(chapter.chapter_id)}. {chapter.title}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label="소분류">
                  {(props) => (
                    <select
                      {...props}
                      value={newSubId}
                      disabled={subChapters.length === 0}
                      onChange={(e) => setNewSubId(e.target.value)}
                    >
                      <option value="">
                        {!newTopId
                          ? "대분류를 먼저 고르세요"
                          : subChapters.length === 0
                            ? "하위 업무 없음"
                            : "대분류 전체"}
                      </option>
                      {subChapters.map((sub) => (
                        <option key={sub.chapter_id} value={sub.chapter_id}>
                          {outline.numbers.get(sub.chapter_id)}. {sub.title}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
              </div>

              <Field
                label="할 일"
                hint="업무를 연결하면 신입이 그 본문을 바로 열어볼 수 있고, 리포트의 완료–이해 불일치 신호에도 잡힙니다."
              >
                {(props) => (
                  <input
                    {...props}
                    type="text"
                    placeholder={
                      newSubId || newTopId
                        ? `예: ${chapterTitle(newSubId || newTopId)} 절차대로 1회 해보기`
                        : "예: 주간 회의 참석하기"
                    }
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                  />
                )}
              </Field>
              <div className="actions actions-end">
                <Button type="submit" variant="primary" disabled={!newTitle.trim() || busy}>
                  추가
                </Button>
              </div>
            </form>
          </div>
        </>
      )}

      {viewingChapterId && (
        <ChapterViewer
          chapters={chapters}
          chapterId={viewingChapterId}
          answer={null}
          onClose={() => setViewingChapterId(null)}
        />
      )}
    </>
  );
}

export default ChecklistManagePage;
