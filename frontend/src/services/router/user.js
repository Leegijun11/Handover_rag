import apiClient from "../../api/client";

// backend/routers/user.py와 1:1 대응 (guidelines 5-2)
export function register(payload) {
  return apiClient.post("/user/register", payload);
}

export function login(payload) {
  return apiClient.post("/user/login", payload);
}

export function getUser(userId) {
  return apiClient.get(`/user/${userId}`);
}

export function deleteUser(userId) {
  return apiClient.delete(`/user/${userId}`);
}
