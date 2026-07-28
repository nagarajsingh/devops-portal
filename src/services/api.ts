import type { AuthSession, PipelineRequest, PipelineRequestInput, ReviewUpdate, Role } from "../types";

const API_BASE = "/devops-portal/api";

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    const detail = typeof body.detail === "string" ? body.detail : body.detail?.message ?? "Request failed";
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function login(username: string, password: string, role: Role): Promise<AuthSession> {
  return request<AuthSession>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password, role }),
  });
}

export function getNamespaces(token: string): Promise<string[]> {
  return request<string[]>("/namespaces", {}, token);
}

export function createPipelineRequest(payload: PipelineRequestInput, token: string): Promise<PipelineRequest> {
  return request<PipelineRequest>("/requests", {
    method: "POST",
    body: JSON.stringify(payload),
  }, token);
}

export function getPipelineRequests(token: string): Promise<PipelineRequest[]> {
  return request<PipelineRequest[]>("/requests", {}, token);
}

export function updatePipelineRequest(id: string, payload: ReviewUpdate, token: string): Promise<PipelineRequest> {
  return request<PipelineRequest>(`/requests/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  }, token);
}

export function approvePipelineRequest(id: string, token: string): Promise<PipelineRequest> {
  return request<PipelineRequest>(`/requests/${id}/approve`, { method: "POST" }, token);
}

export function rejectPipelineRequest(id: string, reason: string, token: string): Promise<PipelineRequest> {
  return request<PipelineRequest>(`/requests/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  }, token);
}
