import { useEffect, useState } from "react";
import { getAssignmentsByMentor } from "../../services/router/assignment";
import { getUser } from "../../services/router/user";

/**
 * 사수가 담당 신입을 고르는 선택 바.
 *
 * 체크리스트 관리와 리포트가 둘 다 신입 1명 단위 화면인데 사수는 여러 명을 담당해서,
 * 두 화면이 같은 선택 UI를 쓴다.
 *
 * 목록은 Assignment에서 온다 — 배정된 신입만 나온다는 뜻이고, 이 화면들에는 그게 맞다.
 * 체크리스트 초안 생성도 리포트도 배정된 문서가 있어야 성립하기 때문이다.
 * 이름은 배정 응답에 없어서 한 건씩 따로 조회한다 (guidelines 4-3).
 *
 * onChange에는 assignment를 통째로 넘긴다 — 호출부가 document_id도 함께 필요하다.
 */
function NewcomerPicker({ mentorId, value, onChange, children }) {
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const { data } = await getAssignmentsByMentor(mentorId);
        const withNames = await Promise.all(
          (data || []).map(async (assignment) => {
            try {
              const { data: user } = await getUser(assignment.newcomer_id);
              return { ...assignment, name: user.name };
            } catch {
              return { ...assignment, name: assignment.newcomer_id };
            }
          }),
        );
        if (cancelled) return;
        setOptions(withNames);
        // 첫 진입에 아무도 선택돼 있지 않으면 첫 신입을 고른다.
        if (!value && withNames.length) onChange(withNames[0]);
      } catch (err) {
        if (!cancelled) setError(err.userMessage || "담당 신입 목록을 불러오지 못했습니다");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
    // value/onChange는 의도적으로 제외 — 신입을 바꿀 때마다 목록을 다시 부를 이유가 없다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mentorId]);

  if (loading) return <div className="empty">담당 신입을 불러오는 중…</div>;
  if (error) return <div className="banner banner-error">{error}</div>;
  if (!options.length) {
    return (
      <div className="empty">
        아직 배정한 신입이 없습니다. 먼저 신입 배정 화면에서 문서를 배정하세요.
      </div>
    );
  }

  return (
    <div className="subject-bar">
      <label htmlFor="newcomer-picker">담당 신입</label>
      <select
        id="newcomer-picker"
        value={value?.newcomer_id || ""}
        onChange={(e) =>
          onChange(options.find((o) => o.newcomer_id === e.target.value))
        }
      >
        {options.map((option) => (
          <option key={option.newcomer_id} value={option.newcomer_id}>
            {option.name}
          </option>
        ))}
      </select>
      {children}
    </div>
  );
}

export default NewcomerPicker;
