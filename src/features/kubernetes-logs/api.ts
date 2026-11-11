import type {
  KubernetesLogAccess,
  KubernetesLogCluster,
  KubernetesLogPod,
  KubernetesLogResponse,
  LogOutputFormat,
  LogWindow,
} from "./types";

const API_BASE = "/devops-portal/api";

async function api<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(typeof body.detail === "string" ? body.detail : "Request failed");
  }
  return response.json() as Promise<T>;
}

export const getLogClusters = (token: string) =>
  api<KubernetesLogCluster[]>("/kubernetes-logs/clusters", token);

export const getLogNamespaces = (cluster: string, token: string) =>
  api<string[]>(`/kubernetes-logs/namespaces/${encodeURIComponent(cluster)}`, token);

export const getManageableLogNamespaces = (cluster: string, token: string) =>
  api<string[]>(`/kubernetes-logs/admin/namespaces/${encodeURIComponent(cluster)}`, token);

export const getLogAccess = (token: string) =>
  api<KubernetesLogAccess>("/kubernetes-logs/access", token);

export const updateLogAccess = (cluster: string, namespaces: string[], token: string) =>
  api<{ cluster: string; namespaces: string[] }>(
    `/kubernetes-logs/access/${encodeURIComponent(cluster)}`,
    token,
    { method: "PUT", body: JSON.stringify({ namespaces }) },
  );

export const getLogPods = (cluster: string, namespace: string, token: string) => {
  const query = new URLSearchParams({ cluster, namespace });
  return api<KubernetesLogPod[]>(`/kubernetes-logs/pods?${query.toString()}`, token);
};

export const getPodLogs = (
  cluster: string,
  namespace: string,
  pod: string,
  container: string,
  window: LogWindow,
  format: LogOutputFormat,
  includePrevious: boolean,
  token: string,
) => {
  const query = new URLSearchParams({
    cluster,
    namespace,
    pod,
    container,
    window,
    format,
    include_previous: String(includePrevious),
  });
  return api<KubernetesLogResponse>(`/kubernetes-logs/logs?${query.toString()}`, token);
};

export async function downloadPodLogs(
  cluster: string,
  namespace: string,
  pod: string,
  container: string,
  window: LogWindow,
  format: LogOutputFormat,
  includePrevious: boolean,
  token: string,
) {
  const query = new URLSearchParams({
    cluster,
    namespace,
    pod,
    container,
    window,
    format,
    include_previous: String(includePrevious),
  });
  const response = await fetch(`${API_BASE}/kubernetes-logs/download?${query.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Unable to download logs" }));
    throw new Error(typeof body.detail === "string" ? body.detail : "Unable to download logs");
  }
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] || `${pod}-logs.${format === "json" ? "json" : format === "text" ? "txt" : "log"}`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
