import { useRef, useState } from "react";
import { uploadDocumentChapters, uploadDocumentFile } from "../../services/router/document";
import { getCurrentUser } from "../../api/session";
import { rememberUploadedDocument } from "../../api/documentHistory";
import Button from "../../components/common/Button";
import Field from "../../components/common/Field";

const MAX_FILE_BYTES = 10 * 1024 * 1024; // 서버와 같은 상한 (guidelines 5-9)
const ACCEPTED = ".txt,.md";

function newChapter() {
  // key는 React 목록용 — 제목이 비었거나 겹쳐도 입력 중 순서가 흔들리지 않게 한다.
  return { key: crypto.randomUUID(), title: "", content: "" };
}

function UploadPage() {
  const mentor = getCurrentUser();
  const fileInputRef = useRef(null);

  const [tab, setTab] = useState("file"); // file | manual
  const [file, setFile] = useState(null);
  const [chapters, setChapters] = useState([newChapter(), newChapter()]);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function switchTab(next) {
    setTab(next);
    setError("");
    setResult(null);
  }

  function pickFile(picked) {
    setError("");
    setResult(null);
    if (!picked) return setFile(null);
    if (picked.size > MAX_FILE_BYTES) {
      setFile(null);
      return setError("파일 크기는 10MB를 넘을 수 없습니다");
    }
    setFile(picked);
  }

  function updateChapter(key, patch) {
    setChapters((prev) => prev.map((c) => (c.key === key ? { ...c, ...patch } : c)));
  }

  const filledChapters = chapters.filter((c) => c.title.trim() && c.content.trim());

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const { data } =
        tab === "file"
          ? await uploadDocumentFile(mentor.user_id, file)
          : await uploadDocumentChapters(
              mentor.user_id,
              filledChapters.map(({ title, content }) => ({
                title: title.trim(),
                content: content.trim(),
              })),
            );
      setResult(data);
      // 문서 목록 API가 없어서, 배정 화면이 쓸 수 있도록 여기서 받은 document_id를
      // 브라우저에 남긴다 (api/documentHistory.js 주석 참고).
      rememberUploadedDocument(mentor.user_id, {
        documentId: data.document_id,
        chapterTitles: (data.chapters || []).map((c) => c.title),
      });
      // 성공한 입력은 비워서, 같은 문서를 두 번 올리는 실수를 줄인다.
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setChapters([newChapter(), newChapter()]);
    } catch (err) {
      setError(err.userMessage || "업로드에 실패했습니다");
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = tab === "file" ? Boolean(file) : filledChapters.length > 0;

  return (
    <>
      <h3 className="page-title">인수인계서 업로드</h3>
      <p className="page-desc">
        챗봇이 답변의 근거로 삼을 문서입니다. 업로드하면 업무 단위로 나눠 저장됩니다.
      </p>

      <div className="tabs">
        <button
          type="button"
          aria-selected={tab === "file"}
          onClick={() => switchTab("file")}
        >
          파일 업로드
        </button>
        <button
          type="button"
          aria-selected={tab === "manual"}
          onClick={() => switchTab("manual")}
        >
          직접 입력
        </button>
      </div>

      {error && <div className="banner banner-error">{error}</div>}

      {result && (
        <div className="banner banner-info">
          업무 {result.chapters?.length ?? 0}개로 나눠 저장했습니다. 이제 신입 배정 화면에서 이
          문서를 배정할 수 있습니다.
        </div>
      )}

      <form onSubmit={handleSubmit}>
        {tab === "file" ? (
          <>
            <label
              className="dropzone"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                pickFile(e.dataTransfer.files?.[0]);
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED}
                hidden
                onChange={(e) => pickFile(e.target.files?.[0])}
              />
              <p>{file ? file.name : "파일을 끌어다 놓거나 클릭해서 선택하세요"}</p>
              <span className="hint">
                {file
                  ? `${(file.size / 1024).toFixed(1)} KB · 다시 선택하려면 클릭하세요`
                  : ".txt, .md · 최대 10MB · 목차를 자동으로 인식합니다"}
              </span>
            </label>
          </>
        ) : (
          <div className="card">
            {chapters.map((chapter, index) => (
              <div key={chapter.key}>
                <Field label={`업무 ${index + 1} · 제목`}>
                  {(props) => (
                    <input
                      {...props}
                      type="text"
                      placeholder="예: 상품 등록 절차"
                      value={chapter.title}
                      onChange={(e) => updateChapter(chapter.key, { title: e.target.value })}
                    />
                  )}
                </Field>
                <Field label={`업무 ${index + 1} · 내용`}>
                  {(props) => (
                    <textarea
                      {...props}
                      placeholder="인수인계할 내용을 적어주세요"
                      value={chapter.content}
                      onChange={(e) => updateChapter(chapter.key, { content: e.target.value })}
                    />
                  )}
                </Field>
                {chapters.length > 1 && (
                  <div className="actions actions-end" style={{ marginTop: 0 }}>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() =>
                        setChapters((prev) => prev.filter((c) => c.key !== chapter.key))
                      }
                    >
                      이 업무 삭제
                    </Button>
                  </div>
                )}
                <hr
                  style={{
                    border: 0,
                    borderTop: "1px solid var(--border)",
                    margin: "16px 0",
                  }}
                />
              </div>
            ))}

            <div className="actions">
              <Button onClick={() => setChapters((prev) => [...prev, newChapter()])}>
                + 업무 추가
              </Button>
            </div>
          </div>
        )}

        <div className="actions actions-end">
          <Button type="submit" variant="primary" disabled={!canSubmit || submitting}>
            {submitting ? "업로드 중…" : "업로드"}
          </Button>
        </div>
        {submitting && (
          <p className="hint" style={{ textAlign: "right" }}>
            업무별로 나눠 임베딩까지 만드는 중이라 시간이 걸립니다.
          </p>
        )}
      </form>
    </>
  );
}

export default UploadPage;
