export type MonitoringSection = "overview" | "kubernetes" | "project" | "pipelines" | "deployments" | "provisioning" | "exceptions";

export interface MonitoringCard {
  key: string;
  label: string;
  value: number;
  detail: string;
  tone: "primary" | "neutral" | "healthy" | "warning" | "progress" | "danger";
}

export interface DeploymentDetail {
  name: string;
  desired: number;
  available: number;
  unavailable: number;
  status: string;
}

export interface NamespaceMonitoringSummary {
  name: string;
  services: number;
  ingresses: number;
  deployments?: number;
  service_names: string[];
  ingress_names: string[];
  deployment_details?: DeploymentDetail[];
}

export interface PersistentVolumeSummary {
  name: string;
  capacity_gib: number;
  allocated_gib: number;
  available_gib: number;
  status: string;
  storage_class: string;
  access_modes: string[];
  claim: string;
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
  deployments?: number;
  deployments_healthy?: number;
  deployments_unhealthy?: number;
  namespace_details: NamespaceMonitoringSummary[];
  persistent_volumes?: PersistentVolumeSummary[];
  storage?: { capacity_gib: number; allocated_gib: number; available_gib: number };
  source?: string;
}

export interface PipelineRun {
  id: number;
  name: string;
  build_number?: string;
  release_name?: string;
  environment?: string;
  status: string;
  result?: string;
  reason?: string;
  pipeline_type?: string;
  queue_time?: string;
  start_time?: string;
  finish_time?: string;
  started_on?: string;
  completed_on?: string;
  requested_by?: string;
  url?: string;
}

export interface LivePipelineMetrics {
  days: number;
  from: string;
  to: string;
  definitions: number;
  running: number;
  queued: number;
  builds_completed: number;
  builds_succeeded: number;
  builds_failed: number;
  running_runs: PipelineRun[];
  queued_runs: PipelineRun[];
  completed_runs: PipelineRun[];
  yaml: {
    definitions: number;
    running: number;
    queued: number;
    completed: number;
    failed: number;
    runs: PipelineRun[];
  };
  classic: {
    definitions: number;
    running: number;
    pending: number;
    completed: number;
    failed: number;
    deployments: PipelineRun[];
    error?: string;
  };
  source: string;
  collected_at: string;
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
  queued?: number;
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
  live_pipeline_metrics?: LivePipelineMetrics;
  pipeline_live_error?: string;
  kubernetes_live_error?: string;
  deployment_metrics: DeploymentMetrics;
  provisioning_metrics: ProvisioningMetrics;
  request_statuses: Record<string, number>;
  provisioning_activity: ProvisioningActivity[];
  recent_failures: MonitoringFailure[];
}
