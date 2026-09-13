import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { getCurrentUser } from "../../api/session";
import { getAssignmentByNewcomer } from "../../services/router/assignment";
import { getChecklist } from "../../services/router/checklist";
import { getUser } from "../../services/router/user";

/**
 * 신입 화면 두 개(챗봇·체크리스트)와 앱 셸이 함께 쓰는 배정 정보 + 체크리스트 목록.
 *
 * 왜 한곳에 모으나: 셋 다 같은 값이 필요한데 통합 API가 없어서 매번 두 번씩 불러야 한다
 * (guidelines 4-3 — GET /assignment?newcomer_id= 로 mentor_id를 받고, GET /user/{mentor_id}로
 * 이름을 한 번 더). 화면마다 따로 부르면 같은 요청이 세 번 나가고, 헤더의 사수 이름과
 * 본문의 배정 정보가 서로 다른 시점의 값이 될 수도 있다.
 *
 * - 셸(AppShell)     : mentorName — 헤더의 "사수 김사수", checklistItems — 좌측 메뉴 요약
 * - 챗봇(ChatPage)   : document_id — 출처 칩에 붙일 챕터 목록 조회에 필요
 * - 체크리스트       : mentorName — "사수 김사수 님이 작성했습니다", checklistItems — 본문 목록
 *
 * checklistItems를 셸(체크리스트 화면 바깥)과 체크리스트 화면이 함께 쓰기 때문에, 체크
 * 완료/취소도 화면 로컬 상태가 아니라 여기 refreshChecklist를 거친다 — 그래야 좌측 메뉴
 * 요약이 체크리스트 화면과 같은 시점의 값을 보여준다.
 *
 * 사수 화면에는 이 Provider를 씌우지 않는다. 그때는 기본값이 그대로 쓰여서
 * 셸이 사수 이름 칸을 비워두고, checklistItems도 빈 배열로 남는다.
 */

const EMPTY = {
  assignment: null,
  mentorName: "",
  loading: false,
  error: "",
  /** 배정 자체가 아직 없는 상태(404). 에러가 아니라 정상적인 초기 상태다. */
  unassigned: false,
};

const NewcomerScopeContext = createContext({
  ...EMPTY,
  checklistItems: [],
  checklistLoading: false,
  checklistError: "",
  refreshChecklist: () => {},
});

export function useNewcomerScope() {
  return useContext(NewcomerScopeContext);
}

function NewcomerScope({ children }) {
  const user = getCurrentUser();
  const newcomerId = user?.user_id;
  const [scope, setScope] = useState({ ...EMPTY, loading: true });
  const [checklistItems, setChecklistItems] = useState([]);
  const [checklistLoading, setChecklistLoading] = useState(true);
  const [checklistError, setChecklistError] = useState("");

  const refreshChecklist = useCallback(async () => {
    if (!newcomerId) return;
    setChecklistLoading(true);
    try {
      const { data } = await getChecklist(newcomerId);
      setChecklistItems(data || []);
      setChecklistError("");
    } catch (err) {
      setChecklistError(err.userMessage || "체크리스트를 불러오지 못했습니다");
    } finally {
      setChecklistLoading(false);
    }
  }, [newcomerId]);

  useEffect(() => {
    if (!newcomerId) return undefined;
    let cancelled = false;

    async function load() {
      try {
        const { data: assignment } = await getAssignmentByNewcomer(newcomerId);

        // 이름 조회는 실패해도 화면을 막지 않는다 — 배정 정보만으로 챗봇·체크리스트는 돌아간다.
        let mentorName = "";
        try {
          const { data: mentor } = await getUser(assignment.mentor_id);
          mentorName = mentor.name;
        } catch {
          mentorName = "";
        }

        if (!cancelled) {
          setScope({ ...EMPTY, assignment, mentorName });
        }
      } catch (err) {
        // 404는 "아직 사수가 문서를 배정하지 않았다"는 뜻이라 에러 문구를 띄우지 않는다.
        const unassigned = err.response?.status === 404;
        if (!cancelled) {
          setScope({
            ...EMPTY,
            unassigned,
            error: unassigned ? "" : err.userMessage || "배정 정보를 불러오지 못했습니다",
          });
        }
      }
    }

    load();
    refreshChecklist();
    return () => {
      cancelled = true;
    };
  }, [newcomerId, refreshChecklist]);

  return (
    <NewcomerScopeContext.Provider
      value={{ ...scope, checklistItems, checklistLoading, checklistError, refreshChecklist }}
    >
      {children}
    </NewcomerScopeContext.Provider>
  );
}

export default NewcomerScope;
