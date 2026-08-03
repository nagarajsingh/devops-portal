export interface MonitoringCard {
  label: string;
  value: number;
  tone: "primary" | "neutral" | "healthy" | "warning" | "progress" | "danger";
}

export interface ClusterMonitoringSummary {
  name: string;
  mode: string;
  status: "Healthy" | "Warning" | "Stale" | "Missing";
  collected_at?: string | null;
  age_minutes?: number | null;
  namespaces: number;
  services: number;
  ingresses: number;
}

export interface MonitoringFailure {
  id: string;
  repository: string;
  application: string;
  status: string;
  updated_at?: string;
  detail?: string;
}

export interface MonitoringSummary {
  generated_at: string;
  inventory_generated_at?: string | null;
  cards: MonitoringCard[];
  clusters: ClusterMonitoringSummary[];
  request_statuses: Record<string, number>;
  recent_failures: MonitoringFailure[];
}
