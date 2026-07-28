import type { AuthSession, PipelineRequest, PipelineRequestInput, Role } from "../types";

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
    throw new Error(body.detail ?? `Request failed with status ${response.status}`);
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
