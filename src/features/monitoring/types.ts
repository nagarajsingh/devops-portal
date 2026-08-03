export type MonitoringSection = "overview" | "kubernetes" | "pipelines" | "deployments" | "provisioning" | "exceptions";

export interface MonitoringCard {
  key: string;
  label: string;
  value: number;
  detail: string;
  tone: "primary" | "neutral" | "healthy" | "warning" | "progress" | "danger";
}

export interface NamespaceMonitoringSummary {
  name: string;
  services: number;
  ingresses: number;
  service_names: string[];
  ingress_names: string[];
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
  namespace_details: NamespaceMonitoringSummary[];
}

export interface MonitoringFailure {
  id: string;
  repository: string;
  application: string;
  status: string;
  updated_at?: string;
  detail?: string;
}

export interface ProvisioningActivity {
  id: string;
  repository: string;
  application: string;
  target_cluster: string;
  status: string;
  updated_at?: string;
  pipeline_status: string;
  release_status: string;
  service_status: string;
  ingress_status: string;
}

export interface PipelineMetrics {
  running: number;
  build_created: number;
  release_created: number;
  build_failed: number;
  release_failed: number;
}

export interface DeploymentMetrics {
  completed: number;
  direct: number;
  pipeline_based: number;
  services_completed: number;
  ingresses_completed: number;
}

export interface ProvisioningMetrics {
  pending_approval: number;
  approved: number;
  running: number;
  completed: number;
  failed_partial: number;
}

export interface MonitoringSummary {
  generated_at: string;
  inventory_generated_at?: string | null;
  cards: MonitoringCard[];
  clusters: ClusterMonitoringSummary[];
  pipeline_metrics: PipelineMetrics;
  deployment_metrics: DeploymentMetrics;
  provisioning_metrics: ProvisioningMetrics;
  request_statuses: Record<string, number>;
  provisioning_activity: ProvisioningActivity[];
  recent_failures: MonitoringFailure[];
}
