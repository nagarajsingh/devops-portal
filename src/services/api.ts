import type { ApplicationType, AuthSession, KubernetesService, KubernetesTarget, PipelineRequest, PipelineRequestInput, ReviewUpdate, Role } from "../types";

const API_BASE = "/devops-portal/api";

export class ApiError extends Error {
  code?: string;
  status?: number;
  payload?: unknown;

  constructor(message: string, options: { code?: string; status?: number; payload?: unknown } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = options.code;
    this.status = options.status;
    this.payload = options.payload;
  }
}

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
    const detailBody = body?.detail;
    const detail = typeof detailBody === "string" ? detailBody : detailBody?.message ?? "Request failed";
    throw new ApiError(detail, {
      code: typeof detailBody === "object" && detailBody ? detailBody.code : undefined,
      status: response.status,
      payload: detailBody,
    });
  }

  return response.json() as Promise<T>;
}

export function login(username: string, password: string, role: Role): Promise<AuthSession> {
  return request<AuthSession>("/auth/login", { method: "POST", body: JSON.stringify({ username, password, role }) });
}

export function getApplicationOwners(token: string): Promise<Record<ApplicationType, string>> {
  return request<Record<ApplicationType, string>>("/configuration/app-owners", {}, token);
}

export function getKubernetesTargets(token: string): Promise<KubernetesTarget[]> {
  return request<KubernetesTarget[]>("/configuration/kubernetes-targets", {}, token);
}

export function getNamespaces(token: string, targetCluster = "local-cluster"): Promise<string[]> {
  return request<string[]>(`/namespaces/${encodeURIComponent(targetCluster)}`, {}, token);
}

export function getIngresses(namespace: string, token: string, targetCluster = "local-cluster"): Promise<string[]> {
  return request<string[]>(`/ingresses/${encodeURIComponent(targetCluster)}/${encodeURIComponent(namespace)}`, {}, token);
}

export function getServices(namespace: string, token: string, targetCluster = "local-cluster"): Promise<KubernetesService[]> {
  return request<KubernetesService[]>(`/services/${encodeURIComponent(targetCluster)}/${encodeURIComponent(namespace)}`, {}, token);
}

export function createPipelineRequest(payload: PipelineRequestInput, token: string): Promise<PipelineRequest> {
  return request<PipelineRequest>("/requests", { method: "POST", body: JSON.stringify(payload) }, token);
}

export function getPipelineRequests(token: string): Promise<PipelineRequest[]> {
  return request<PipelineRequest[]>("/requests", {}, token);
}

export function updatePipelineRequest(id: string, payload: ReviewUpdate, token: string): Promise<PipelineRequest> {
  return request<PipelineRequest>(`/requests/${id}`, { method: "PUT", body: JSON.stringify(payload) }, token);
}

export function approvePipelineRequest(id: string, azureDevOpsPat: string, token: string): Promise<PipelineRequest> {
  return request<PipelineRequest>(`/requests/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ azure_devops_pat: azureDevOpsPat }),
  }, token);
}

export function confirmExistingRepository(id: string, azureDevOpsPat: string, token: string): Promise<PipelineRequest> {
  return request<PipelineRequest>(`/requests/${id}/confirm-existing-repository`, {
    method: "POST",
    body: JSON.stringify({ azure_devops_pat: azureDevOpsPat }),
  }, token);
}

export function rejectPipelineRequest(id: string, reason: string, token: string): Promise<PipelineRequest> {
  return request<PipelineRequest>(`/requests/${id}/reject`, { method: "POST", body: JSON.stringify({ reason }) }, token);
}

export function closePipelineRequest(id: string, comment: string, token: string): Promise<PipelineRequest> {
  return request<PipelineRequest>(`/requests/${id}/close`, { method: "POST", body: JSON.stringify({ comment }) }, token);
}
