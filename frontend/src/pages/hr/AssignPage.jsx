import { useCallback, useEffect, useState } from "react";
import {
  createAssignment,
  getAssignmentsByMentor,
} from "../../services/router/assignment";
import { getUser } from "../../services/router/user";
import { getChapters, listMyDocuments } from "../../services/router/document";
import { getCurrentUser } from "../../api/session";
import Button from "../../components/common/Button";
import ChapterViewer from "../../components/common/ChapterViewer";
import Field from "../../components/common/Field";

function formatDate(value) {
  if (!value) return "-";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleDateString("ko-KR");
}

function AssignPage() {
  const mentor = getCurrentUser();

  // GET /document?mentor_id= (guidelines 3-2 신설) — 이전엔 이 브라우저의 localStorage만
  // 봐서 다른 브라우저/기기에서 올린 문서가 안 보였다. 이제 DB에서 직접 받아온다.
  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");

  const [newcomerId, setNewcomerId] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  // 문서에는 이름 필드가 없어서 목록만 봐서는 어떤 문서인지 확신하기 어렵다.
  // 눌렀을 때만 챕터를 받아와 본문을 보여준다.
  const [viewing, setViewing] = useState(null); // { documentId, chapters }
  const [viewingId, setViewingId] = useState("");

  useEffect(() => {
    let cancelled = false;
    listMyDocuments(mentor.user_id)
      .then(({ data }) => {
        if (cancelled) return;
        setDocuments(data || []);
        // 처음 불러왔을 때만 첫 문서를 기본 선택해둔다 — 이후 사용자가 고른 값은
        // 목록이 새로고침돼도 건드리지 않는다.
        setDocumentId((prev) => prev || data?.[0]?.document_id || "");
      })
      .catch(() => !cancelled && setDocuments([]))
      .finally(() => !cancelled && setDocumentsLoading(false));
    return () => {
      cancelled = true;
    };
  }, [mentor.user_id]);

  const load = useCallback(async () => {
    setLoading(true);
    setListError("");
    try {
      const { data } = await getAssignmentsByMentor(mentor.user_id);
      // 배정 응답에는 신입 이름이 없어서 이름은 한 건씩 따로 조회한다
      // (통합 API 없음 — guidelines 4-3). 한 명이 실패해도 목록 전체가 깨지지 않게 한다.
      const withNames = await Promise.all(
        (data || []).map(async (assignment) => {
          try {
            const { data: user } = await getUser(assignment.newcomer_id);
            return { ...assignment, newcomerName: user.name, newcomerEmail: user.email };
          } catch {
            return { ...assignment, newcomerName: null };
          }
        }),
      );
      setRows(withNames);
    } catch (err) {
      setListError(err.userMessage || "배정 현황을 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  }, [mentor.user_id]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError("");
    setNotice("");
    setSubmitting(true);
    try {
      const { data } = await createAssignment({
        mentor_id: mentor.user_id,
        newcomer_id: newcomerId.trim(),
        document_id: documentId.trim(),
      });
      const reassigned = rows.some((r) => r.assignment_id === data.assignment_id);
      setNotice(
        reassigned
          ? "배정 문서를 교체했습니다. 배정일은 그대로 유지됩니다."
          : "배정했습니다. 이제 이 신입이 챗봇에 질문할 수 있습니다.",
      );
      setNewcomerId("");
      await load();
    } catch (err) {
      setFormError(err.userMessage || "배정에 실패했습니다");
    } finally {
      setSubmitting(false);
    }
  }

  async function openDocument(id) {
    setViewingId(id);
    setListError("");
    try {
      const { data } = await getChapters(id);
      if (!data?.length) {
        setListError("이 문서에 등록된 업무가 없습니다");
        return;
      }
      setViewing({ documentId: id, chapters: data });
    } catch (err) {
      setListError(err.userMessage || "본문을 불러오지 못했습니다");
    } finally {
      setViewingId("");
    }
  }

  const canSubmit = newcomerId.trim() && documentId.trim();

  return (
    <>
      <h3 className="page-title">담당 신입 배정</h3>
      <p className="page-desc">
        신입은 배정된 문서 범위 안에서만 챗봇에 질문할 수 있습니다.
      </p>

      <form className="card" onSubmit={handleSubmit}>
        <p className="card-title">새 배정</p>

        {formError && <div className="banner banner-error">{formError}</div>}
        {notice && <div className="banner banner-info">{notice}</div>}

        <div className="row-2">
          <Field
            label="신입사원 ID"
            hint="신입 본인에게 받아서 입력하세요"
          >
            {(props) => (
              <input
                {...props}
                type="text"
                placeholder="예: 3f2b9c14-…"
                value={newcomerId}
                onChange={(e) => setNewcomerId(e.target.value)}
              />
            )}
          </Field>

          <Field
            label="인수인계서"
            hint={
              documentsLoading
                ? "불러오는 중…"
                : documents.length
                  ? "내가 올린 문서 목록입니다"
                  : "먼저 인수인계서를 업로드하거나 document_id를 직접 입력하세요"
            }
          >
            {(props) =>
              documents.length ? (
                <select
                  {...props}
                  value={documentId}
                  onChange={(e) => setDocumentId(e.target.value)}
                >
                  {documents.map((doc) => (
                    <option key={doc.document_id} value={doc.document_id}>
                      {doc.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  {...props}
                  type="text"
                  placeholder="document_id"
                  value={documentId}
                  onChange={(e) => setDocumentId(e.target.value)}
                />
              )
            }
          </Field>
        </div>

        <div className="actions actions-end" style={{ marginTop: 4 }}>
          <Button type="submit" variant="primary" disabled={!canSubmit || submitting}>
            {submitting ? "배정 중…" : "배정하기"}
          </Button>
        </div>
      </form>

      <div className="card">
        <p className="card-title">현재 배정 현황</p>

        {listError && <div className="banner banner-error">{listError}</div>}

        {loading ? (
          <div className="empty">불러오는 중…</div>
        ) : rows.length === 0 ? (
          <div className="empty">아직 배정한 신입이 없습니다.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>신입사원</th>
                <th>배정 문서</th>
                <th>배정일</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.assignment_id}>
                  <td>
                    {row.newcomerName || <span className="hint">이름 조회 실패</span>}
                    <div className="hint">{row.newcomerEmail || row.newcomer_id}</div>
                  </td>
                  <td>
                    {documents.find((d) => d.document_id === row.document_id)?.label || (
                      <span className="hint">{row.document_id}</span>
                    )}
                  </td>
                  <td>{formatDate(row.assigned_at)}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <Button
                      size="sm"
                      disabled={viewingId === row.document_id}
                      onClick={() => openDocument(row.document_id)}
                    >
                      {viewingId === row.document_id ? "여는 중…" : "본문 보기"}
                    </Button>{" "}
                    <Button
                      size="sm"
                      onClick={() => {
                        setNewcomerId(row.newcomer_id);
                        setNotice("");
                        setFormError("");
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                    >
                      문서 변경
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="banner banner-info" style={{ marginTop: 16 }}>
        문서를 바꿔도 배정일은 그대로 유지됩니다. 리포트 기간의 기준이 되기 때문입니다.
      </div>

      {viewing && (
        <ChapterViewer
          chapters={viewing.chapters}
          chapterId={viewing.chapters[0].chapter_id}
          answer={null}
          onClose={() => setViewing(null)}
        />
      )}
    </>
  );
}

export default AssignPage;
