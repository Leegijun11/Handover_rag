import { useRef, useState } from "react";
import { uploadDocumentChapters, uploadDocumentFiles } from "../../services/router/document";
import { getCurrentUser } from "../../api/session";
import { HANDOVER_TEMPLATE } from "../../api/handoverTemplate";
import Button from "../../components/common/Button";
import ChapterViewer from "../../components/common/ChapterViewer";
import Field from "../../components/common/Field";

const MAX_FILE_BYTES = 10 * 1024 * 1024; // 서버와 같은 상한 (guidelines 5-9)
const ACCEPTED = ".txt,.md";

function newChapter() {
  // key는 React 목록용 — 제목이 비었거나 겹쳐도 입력 중 순서가 흔들리지 않게 한다.
  return { key: crypto.randomUUID(), title: "", content: "", hint: "" };
}

/** 표준 양식 -> 입력 폼. 안내 문구는 placeholder로만 쓰고 content는 비워둔다
 *  (api/handoverTemplate.js 상단 설명 참고 — 값으로 넣으면 안내 문구가 문서 본문이 된다). */
function templateChapters() {
  return HANDOVER_TEMPLATE.chapters.map((chapter) => ({
    key: crypto.randomUUID(),
    title: chapter.title,
    content: "",
    hint: chapter.hint,
  }));
}

function UploadPage() {
  const mentor = getCurrentUser();
  const fileInputRef = useRef(null);

  const [tab, setTab] = useState("file"); // file | manual
  const [files, setFiles] = useState([]); // 인수인계서가 파일 여러 개로 나뉜 경우 지원 (guidelines 3-2)
  const [label, setLabel] = useState(""); // 목록 화면(배정 드롭다운)용 제목 — 비우면 서버가 기본 규칙으로 계산
  const [chapters, setChapters] = useState([newChapter(), newChapter()]);
  const [usingTemplate, setUsingTemplate] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [reviewing, setReviewing] = useState(false);

  function switchTab(next) {
    setTab(next);
    setError("");
    setResult(null);
  }

  function applyTemplate() {
    setChapters(templateChapters());
    setUsingTemplate(true);
    setError("");
    setResult(null);
  }

  function clearForm() {
    setChapters([newChapter(), newChapter()]);
    setUsingTemplate(false);
  }

  function pickFiles(pickedList) {
    setError("");
    setResult(null);
    const picked = Array.from(pickedList || []);
    if (!picked.length) return;
    // 하나라도 10MB를 넘으면 전체를 거부한다 — 어느 파일만 골라 담았는지 헷갈리는 것보다
    // 낫다 (guidelines 5-9, 서버도 파일 하나 기준으로 같은 상한을 검사).
    const oversized = picked.find((f) => f.size > MAX_FILE_BYTES);
    if (oversized) {
      return setError(`'${oversized.name}' 파일 크기는 10MB를 넘을 수 없습니다`);
    }
    // 여러 번 끌어다 놓거나 다시 선택하면 기존 목록에 더한다 — 한 번에 다 못 골라도
    // 나눠서 쌓을 수 있게.
    setFiles((prev) => [...prev, ...picked]);
  }

  function removeFile(index) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
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
          ? await uploadDocumentFiles(mentor.user_id, files, label)
          : await uploadDocumentChapters(
              mentor.user_id,
              filledChapters.map(({ title, content }) => ({
                title: title.trim(),
                content: content.trim(),
              })),
              label,
            );
      setResult({ ...data, mode: tab });
      // 배정 화면 드롭다운용 대표 라벨은 이제 서버가 업로드 시점에 계산해서 저장한다
      // (routers/document.py, GET /document?mentor_id=) — 브라우저에 따로 안 남겨도
      // 어느 기기에서 로그인해도 배정 화면에서 바로 보인다.
      // 성공한 입력은 비워서, 같은 문서를 두 번 올리는 실수를 줄인다.
      setFiles([]);
      setLabel("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      clearForm();
    } catch (err) {
      setError(err.userMessage || "업로드에 실패했습니다");
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = tab === "file" ? files.length > 0 : filledChapters.length > 0;

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

      {/* 목차를 못 찾으면 서버가 문서 전체를 "전체 내용" 업무 하나로 저장한다.
          답변은 되지만 리포트의 영역별 히트맵이 막대 하나가 되어 신호가 죽는다.
          사수가 그걸 알고 나눠 쓸 수 있게 여기서 짚어준다. */}
      {result && result.mode === "file" && (result.chapters?.length ?? 0) <= 1 ? (
        <div className="banner banner-warn">
          <div>
            <b>목차를 인식하지 못해 문서 전체를 업무 하나로 저장했습니다.</b>
            <br />
            챗봇 답변은 정상적으로 되지만, 업무 구분이 없어 적응도 리포트의 <b>영역별 히트맵</b>을
            읽을 수 없습니다. 파일에 <code>#</code> 제목이나 <code>1.</code> · <code>제1장</code>{" "}
            같은 번호가 있으면 자동으로 나뉩니다.
            <div className="actions" style={{ marginTop: 10 }}>
              <Button
                onClick={() => {
                  switchTab("manual");
                  applyTemplate();
                }}
              >
                표준 양식으로 나눠 다시 올리기
              </Button>
              <Button onClick={() => setReviewing(true)}>저장된 본문 확인</Button>
            </div>
          </div>
        </div>
      ) : (
        result && (
          <div className="banner banner-info">
            <div>
              업무 {result.chapters?.length ?? 0}개로 나눠 저장했습니다. 이제 신입 배정 화면에서 이
              문서를 배정할 수 있습니다.
              {/* 파일 업로드는 서버가 알아서 나누기 때문에, 어떻게 나뉘었는지 눈으로 확인할
                  방법이 여기 말고는 없다. 배정하기 전에 한 번 보고 넘어가게 한다. */}
              <div className="actions" style={{ marginTop: 10 }}>
                <Button size="sm" onClick={() => setReviewing(true)}>
                  저장된 본문 확인
                </Button>
              </div>
            </div>
          </div>
        )
      )}

      {reviewing && result?.chapters?.length > 0 && (
        <ChapterViewer
          chapters={result.chapters}
          chapterId={result.chapters[0].chapter_id}
          answer={null}
          onClose={() => setReviewing(false)}
        />
      )}

      <form onSubmit={handleSubmit}>
        <Field
          label="인수인계서 제목 (선택)"
          hint={
            tab === "file"
              ? "비워두면 첫 파일명(확장자 제외)으로 저장됩니다"
              : "비워두면 첫 번째 업무 제목으로 저장됩니다"
          }
        >
          {(props) => (
            <input
              {...props}
              type="text"
              placeholder="예: 상품팀 인수인계서"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          )}
        </Field>

        {tab === "file" ? (
          <>
            <label
              className="dropzone"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                pickFiles(e.dataTransfer.files);
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED}
                multiple
                hidden
                onChange={(e) => pickFiles(e.target.files)}
              />
              <p>
                {files.length
                  ? "파일을 더 끌어다 놓거나 클릭해서 추가하세요"
                  : "파일을 끌어다 놓거나 클릭해서 선택하세요"}
              </p>
              <span className="hint">
                .txt, .md · 파일당 최대 10MB · 여러 개를 한 번에 올릴 수 있습니다 · # 제목이나
                1. · 제1장 번호를 업무 단위로 인식합니다
              </span>
            </label>

            {/* 목록은 dropzone(label) 밖에 둔다 — 안에 두면 "제거" 버튼을 눌러도
                label의 네이티브 동작 때문에 파일 선택창이 같이 열려버린다. */}
            {files.length > 0 && (
              <ul className="file-picked-list">
                {files.map((f, index) => (
                  <li key={`${f.name}-${index}`}>
                    <span className="name">{f.name}</span>
                    <span className="hint">{(f.size / 1024).toFixed(1)} KB</span>
                    <Button size="sm" variant="danger" onClick={() => removeFile(index)}>
                      제거
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <div className="card">
            {/* 빈 폼을 그대로 내밀면 "무엇부터 써야 하나"에서 막힌다.
                표준 양식으로 뼈대를 먼저 세워주고 채워 넣게 한다. */}
            {usingTemplate ? (
              <div className="starter">
                <div className="starter-body">
                  <p className="starter-title">{HANDOVER_TEMPLATE.name}을 불러왔습니다</p>
                  <p className="starter-desc">
                    해당 없는 업무는 삭제하고, 필요한 업무는 아래에서 추가하세요.
                    내용을 비워둔 업무는 저장되지 않습니다.
                  </p>
                </div>
                <Button onClick={clearForm}>처음부터 쓰기</Button>
              </div>
            ) : (
              <div className="starter">
                <div className="starter-body">
                  <p className="starter-title">무엇부터 써야 할지 모르겠다면</p>
                  <p className="starter-desc">
                    {HANDOVER_TEMPLATE.description} 업무 {HANDOVER_TEMPLATE.chapters.length}개의
                    제목과 작성 안내가 채워진 상태로 시작합니다.
                  </p>
                </div>
                <Button variant="primary" onClick={applyTemplate}>
                  표준 양식으로 시작
                </Button>
              </div>
            )}

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
                {/* 안내 문구는 hint로만 띄운다. 입력을 시작해도 계속 보여야 도움이 된다. */}
                <Field label={`업무 ${index + 1} · 내용`} hint={chapter.hint || undefined}>
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
