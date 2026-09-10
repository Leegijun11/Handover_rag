import { useCallback, useEffect, useState } from "react";

import { getCurrentUser } from "../../api/session";
import { formatDate } from "../../api/datetime";
import {
  completeChecklistItem,
  getChecklist,
  uncompleteChecklistItem,
} from "../../services/router/checklist";
import { getChapters } from "../../services/router/document";
import { useNewcomerScope } from "../../components/common/NewcomerScope";
import ChapterViewer from "../../components/common/ChapterViewer";
import Button from "../../components/common/Button";

/**
 * 신입 체크리스트 확인/완료 (guidelines 3-5, 4-3).
 *
 * 체크는 되돌릴 수 있다. 잘못 눌렀을 때 손쓸 방법이 없으면 체크 자체를 주저하게 되고,
 * 그러면 완료 시각이 실제와 더 멀어진다. 되돌리면 completed_at이 지워져서 리포트의
 * gap_task("완료 체크 후에도 같은 영역을 계속 묻는가")에서도 빠지는데, 이건 "아직
 * 못 끝냈다"는 뜻이니 그렇게 빠지는 게 맞다.
 *
 * /checklist/{id}/uncomplete는 3-5 명세에 없고 팀원 A가 추가한 API다 — 3번 문서 반영은
 * 조장님 확인이 필요하다 (services/router/checklist.js에도 같은 메모가 있다).
 *
 * 완료 여부가 사수 리포트로 간다는 사실은 이 화면에 쓰지 않는다 — 알면 체크 행동 자체가
 * 왜곡돼서 신호가 무의미해진다 (1-7).
 */
function ChecklistPage() {
  const user = getCurrentUser();
  const newcomerId = user?.user_id;
  const { assignment, mentorName } = useNewcomerScope();
  const documentId = assignment?.document_id;

  const [chapters, setChapters] = useState([]);
  const [openChapterId, setOpenChapterId] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // 처리 중인 항목 하나. 값이 있으면 목록 전체의 체크박스를 잠근다 —
  // 응답을 기다리는 동안 다른 항목을 연달아 누르면 어느 것이 반영됐는지 알 수 없다.
  const [pending, setPending] = useState(null);

  const load = useCallback(async () => {
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
    load();
  }, [load]);

  // 항목에 연결된 업무의 본문을 바로 읽을 수 있게 챕터를 미리 받아둔다.
  // 읽어야 체크할 수 있는 항목("○○ 읽어보기")이 여기서 성립한다.
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

  async function handleToggle(item) {
    if (pending) return;
    const done = item.status === "done";
    setPending(item.item_id);
    setError("");
    try {
      if (done) {
        await uncompleteChecklistItem(item.item_id, newcomerId);
      } else {
        await completeChecklistItem(item.item_id, newcomerId);
      }
      await load();
    } catch (err) {
      setError(err.userMessage || (done ? "완료를 취소하지 못했습니다" : "완료 처리에 실패했습니다"));
    } finally {
      setPending(null);
    }
  }

  const doneCount = items.filter((item) => item.status === "done").length;
  const writtenBy = mentorName ? `사수 ${mentorName} 님이 작성했습니다` : "사수가 작성했습니다";

  return (
    <>
      <h3 className="page-title">체크리스트</h3>
      <p className="page-desc">
        {items.length > 0 ? `${items.length}개 중 ${doneCount}개 완료 · ` : ""}
        {writtenBy}
      </p>

      {error && <div className="banner banner-error">{error}</div>}

      {loading ? (
        <div className="empty">불러오는 중…</div>
      ) : error && items.length === 0 ? (
        <div className="actions">
          <Button onClick={load}>다시 불러오기</Button>
        </div>
      ) : items.length === 0 ? (
        <div className="empty">
          아직 등록된 항목이 없습니다.
          <br />
          사수님이 체크리스트를 만들면 여기에 표시됩니다.
        </div>
      ) : (
        <ul className="check-list">
          {items.map((item) => {
            const done = item.status === "done";
            const busy = pending === item.item_id;
            return (
              <li
                key={item.item_id}
                className={[done ? "done" : "", busy ? "busy" : ""].filter(Boolean).join(" ")}
              >
                <input
                  type="checkbox"
                  id={`item-${item.item_id}`}
                  checked={done}
                  // 처리 중에는 목록 전체를 잠근다 — 어느 항목이 반영됐는지 헷갈리지 않게.
                  disabled={Boolean(pending)}
                  onChange={() => handleToggle(item)}
                />
                <div className="body">
                  <label className="title" htmlFor={`item-${item.item_id}`}>
                    {item.title}
                  </label>
                  <div className="meta">
                    {busy
                      ? done
                        ? "완료 취소하는 중…"
                        : "완료 처리 중…"
                      : done
                        ? `${formatDate(item.completed_at)} 완료 · 다시 누르면 취소됩니다`
                        : "아직 완료하지 않았습니다"}
                  </div>
                </div>
                {/* 연결된 업무가 있으면 본문을 바로 열어준다 — 읽고 체크하는 흐름이 한 화면에서 끝난다. */}
                {item.chapter_id && chapters.some((c) => c.chapter_id === item.chapter_id) && (
                  <Button size="sm" onClick={() => setOpenChapterId(item.chapter_id)}>
                    업무 보기
                  </Button>
                )}
                {done && !busy && <span className="badge badge-done">완료</span>}
              </li>
            );
          })}
        </ul>
      )}

      {openChapterId && (
        <ChapterViewer
          chapters={chapters}
          chapterId={openChapterId}
          answer={null}
          onClose={() => setOpenChapterId(null)}
        />
      )}
    </>
  );
}

export default ChecklistPage;
