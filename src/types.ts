export type Role = "developer" | "devops";

export type PageKey =
  | "home"
  | "dashboard"
  | "requests"
  | "file-placement"
  | "monitoring"
  | "ms-portal"
  | "admin";

export interface NavItem {
  key: PageKey;
  label: string;
  devopsOnly?: boolean;
  href?: string;
}

export interface AuthSession {
  access_token: string;
  token_type: string;
  username: string;
  role: Role;
}

export interface PipelineRequestInput {
  application_name: string;
  repository_name: string;
  pipeline_type?: string;
  ingress_path: string;
  create_service: boolean;
  service_name: string;
  service_port: number;
  namespace: string;
  comments?: string;
}

export interface ProvisionStep {
  status: string;
  message?: string;
  id?: string;
  url?: string;
}

export interface TimelineEvent {
  at: string;
  action: string;
  actor: string;
  detail?: string;
}

export interface PipelineRequest extends PipelineRequestInput {
  id: string;
  requested_by: string;
  status: string;
  created_at: string;
  updated_at?: string;
  reviewed_by?: string;
  review_comments?: string;
  original_request?: PipelineRequestInput;
  provisioning?: Record<string, ProvisionStep>;
  timeline?: TimelineEvent[];
}

export interface ReviewUpdate extends PipelineRequestInput {
  review_comments?: string;
}
