export type LogOutputFormat = "standard" | "text" | "json";
export type LogWindow = "live" | "5m" | "10m" | "30m" | "1h" | "5h" | "12h" | "24h" | "3d" | "7d";

export interface KubernetesLogCluster {
  name: string;
  mode: "direct" | "remote-agent";
  enabled_namespaces: number;
}

export interface KubernetesLogPod {
  name: string;
  phase: string;
  containers: string[];
  restarts: number;
  ready: boolean;
  created_at?: string | null;
  node?: string;
}

export interface KubernetesLogResponse {
  content: string;
  format: LogOutputFormat;
  window: LogWindow;
  source: string;
  fetched_at: string;
  truncated: boolean;
  line_count: number;
}

export interface KubernetesLogAccess {
  clusters: Record<string, string[]>;
}
