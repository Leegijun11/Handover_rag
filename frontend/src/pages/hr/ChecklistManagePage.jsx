import { useCallback, useEffect, useState } from "react";
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
import NewcomerPicker from "../../components/hr/NewcomerPicker";
import Button from "../../components/common/Button";
import Field from "../../components/common/Field";

function ChecklistManagePage() {
  const mentor = getCurrentUser();

  const [assignment, setAssignment] = useState(null);
  const [items, setItems] = useState([]);
  const [chapters, setChapters] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // AI 초안은 저장 전까지 화면에만 있는 값이다 (guidelines 3-4 — draft는 저장하지 않음).
  const [draft, setDraft] = useState(null);
  const [drafting, setDrafting] = useState(false);

  // 수정 중인 항목. 모달(prompt) 대신 행을 입력칸으로 바꾼다 — 편집하려는 항목을
  // 계속 보면서 고칠 수 있고, 브라우저 모달이 화면을 막지도 않는다.
  const [editing, setEditing] = useState(null); // { itemId, title }
  const [newTitle, setNewTitle] = useState("");
  const [newChapterId, setNewChapterId] = useState("");
  const [busy, setBusy] = useState(false);

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

  function chapterTitle(chapterId) {
    if (!chapterId) return "연결된 업무 없음";
    return chapters.find((c) => c.chapter_id === chapterId)?.title || chapterId;
  }

  const nextOrder = items.reduce((max, item) => Math.max(max, item.order ?? 0), 0) + 1;

  async function handleDraft() {
    setDrafting(true);
    setError("");
    setNotice("");
    try {
      const { data } = await draftChecklist(documentId);
      // 초안은 전부 선택된 상태로 시작한다 — 사수가 빼는 편이 하나씩 고르는 것보다 빠르다.
      setDraft((data || []).map((c, i) => ({ ...c, key: `${i}-${c.title}`, checked: true })));
    } catch (err) {
      setError(err.userMessage || "초안을 만들지 못했습니다");
    } finally {
      setDrafting(false);
    }
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
          source: "ai_draft",
        })),
      );
      setDraft(null);
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
          chapter_id: newChapterId || null,
          title: newTitle.trim(),
          order: nextOrder,
          source: "manual",
        },
      ]);
      setNewTitle("");
      setNewChapterId("");
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
    setBusy(true);
    try {
      // 두 항목의 order를 맞바꾼다. reorder는 항목 하나의 order만 받으므로 두 번 호출한다.
      await reorderChecklistItem(items[index].item_id, items[target].order);
      await reorderChecklistItem(items[target].item_id, items[index].order);
      await loadItems();
    } catch (err) {
      setError(err.userMessage || "순서를 바꾸지 못했습니다");
    } finally {
      setBusy(false);
    }
  }

  const draftChosen = draft?.filter((d) => d.checked).length ?? 0;

  return (
    <>
      <h3 className="page-title">체크리스트 관리</h3>
      <p className="page-desc">배정한 신입을 골라 체크리스트를 작성합니다.</p>

      <NewcomerPicker mentorId={mentor.user_id} value={assignment} onChange={setAssignment}>
        <span style={{ fontSize: 12, color: "var(--text-faint)", marginLeft: "auto" }}>
          {items.length}개 중 {items.filter((i) => i.status === "done").length}개 완료
        </span>
      </NewcomerPicker>

      {assignment && (
        <>
          {error && <div className="banner banner-error">{error}</div>}
          {notice && <div className="banner banner-info">{notice}</div>}

          <div className="card">
            <p className="card-title">AI 초안</p>
            <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--text-muted)" }}>
              인수인계서에 적힌 업무를 읽고 후보를 뽑아옵니다. 승인하기 전까지는 저장되지 않습니다.
            </p>
            <Button onClick={handleDraft} disabled={drafting || busy}>
              {drafting ? "초안 만드는 중…" : "인수인계서 기반 초안 생성"}
            </Button>

            {draft && (
              <div style={{ marginTop: 16 }}>
                {draft.length === 0 ? (
                  <div className="empty">후보를 만들지 못했습니다.</div>
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
                          <span className="badge badge-ai">AI 초안</span>
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
              <div className="row-2">
                <Field label="직접 추가">
                  {(props) => (
                    <input
                      {...props}
                      type="text"
                      placeholder="예: 배포 절차 문서 읽어보기"
                      value={newTitle}
                      onChange={(e) => setNewTitle(e.target.value)}
                    />
                  )}
                </Field>
                <Field label="연결할 업무 (선택)">
                  {(props) => (
                    <select
                      {...props}
                      value={newChapterId}
                      onChange={(e) => setNewChapterId(e.target.value)}
                    >
                      <option value="">연결 안 함</option>
                      {chapters.map((chapter) => (
                        <option key={chapter.chapter_id} value={chapter.chapter_id}>
                          {chapter.title}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
              </div>
              <div className="actions actions-end">
                <Button type="submit" variant="primary" disabled={!newTitle.trim() || busy}>
                  추가
                </Button>
              </div>
            </form>
          </div>
        </>
      )}
    </>
  );
}

export default ChecklistManagePage;
