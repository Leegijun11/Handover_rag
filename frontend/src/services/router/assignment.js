import apiClient from "../../api/client";

// backend/routers/assignment.py와 1:1 대응
export function createAssignment(payload) {
  return apiClient.post("/assignment", payload);
}

export function getAssignmentByNewcomer(newcomerId) {
  return apiClient.get("/assignment", { params: { newcomer_id: newcomerId } });
}

export function getAssignmentsByMentor(mentorId) {
  return apiClient.get("/assignment", { params: { mentor_id: mentorId } });
}
