import type { MonitoringSummary } from "./types";

const API_BASE = "/devops-portal/api";

export async function getMonitoringSummary(token: string, days = 1): Promise<MonitoringSummary> {
  const response = await fetch(`${API_BASE}/monitoring/summary?days=${encodeURIComponent(days)}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Unable to load monitoring data" }));
    throw new Error(typeof body.detail === "string" ? body.detail : "Unable to load monitoring data");
  }

  return response.json() as Promise<MonitoringSummary>;
}
