export type Role = "developer" | "devops";
export type PageKey = "home"|"dashboard"|"requests"|"file-placement"|"monitoring"|"deployment-management"|"ms-portal"|"devops-tasks"|"datasources"|"profile"|"admin";
export interface NavItem { key:PageKey; label:string; devopsOnly?:boolean; adminOnly?:boolean; href?:string; }
export interface AuthSession { access_token:string; token_type:string; username:string; role:Role; is_admin:boolean; }
export interface PortalUser { id:number; email:string; role:Role; is_admin:boolean; is_active:boolean; created_at:string; updated_at:string; }
export type DevOpsTaskStatus="backlog"|"inprogress"|"completed";
export type DevOpsTaskPriority="low"|"medium"|"high"|"critical";
export interface DevOpsTaskComment{id:string;author:string;text:string;created_at:string;}
export interface DevOpsTask{id:string;title:string;description:string;assignee:string;status:DevOpsTaskStatus;priority:DevOpsTaskPriority;created_by:string;created_at:string;updated_at:string;comments:DevOpsTaskComment[];history:{at:string;actor:string;action:string}[];}
export type ApplicationType="H2H"|"Collections"|"Native-Mobile"|"Safenet";
export interface PipelineRequestInput { application_type:ApplicationType; app_owner:string; repository_name:string; reference_repository_name:string; reference_branch?:string; setup_pipeline:boolean; pipeline_type?:string; ingress_path:string; ingress_name?:string; create_service:boolean; service_name:string; service_port:number; namespace:string; target_cluster:string; comments?:string; }
export interface KubernetesService {name:string;ports:number[];} export interface KubernetesTarget{name:string;mode:"direct"|"azure_pipeline";}
export interface ProvisionStep {status:string;message?:string;id?:string;run_id?:number;url?:string;branch?:string;source_branch?:string;files?:string[];name?:string;yaml_path?:string;target_cluster?:string;requires_confirmation?:boolean;confirmation_action?:string;}
export interface TimelineEvent{at:string;action:string;actor:string;detail?:string;}
export interface PipelineRequest extends PipelineRequestInput{id:string;requested_by:string;status:string;created_at:string;updated_at?:string;reviewed_by?:string;review_comments?:string;closure_comment?:string;app_owner_decision_by?:string;app_owner_decision_at?:string;app_owner_comment?:string;original_request?:PipelineRequestInput;provisioning?:Record<string,ProvisionStep>;timeline?:TimelineEvent[];}
export interface ReviewUpdate extends PipelineRequestInput{review_comments?:string;}


export interface DatasourceEntityProfile {
  id:number;
  entity_code:string;
  service_id:string;
  db_host:string;
  db_port:number;
  ons_nodes:string;
  password_pattern_configured:boolean;
  updated_at?:string;
}

export interface WebLogicEnvironment {
  id:number;
  application:string;
  environment:string;
  instance_name:string;
  base_path:string;
  domain_name:string;
  admin_host:string;
  admin_port:number;
  ssh_port:number;
  wlst_path:string;
  agent_pool:string;
  default_db_host:string;
  default_db_port:number;
  default_ons_nodes:string;
  is_production:boolean;
  is_active:boolean;
  weblogic_username:string;
  weblogic_password_configured:boolean;
  ssh_username:string;
  ssh_password_configured:boolean;
  entities:DatasourceEntityProfile[];
  created_at:string;
  updated_at:string;
}

export interface DatasourcePlanItem {
  source_name:string;
  target_name:string;
  source_jndis:string[];
  target_jndis:string[];
  source_user:string;
  target_user:string;
  source_url:string;
  target_url:string;
  driver_name:string;
  source_targets:string[];
  target_targets:string[];
  fan_enabled:boolean;
  ons_nodes:string;
  status:string;
  missing_targets?:string[];
}

export interface DatasourcePlan {
  request_id:string;
  application:string;
  environment:string;
  domain_name:string;
  action:string;
  datasource_type:string;
  reference_entity:string;
  target_entity:string;
  datasources:DatasourcePlanItem[];
}

export interface DatasourceOperation {
  id:number;
  request_id:string;
  environment_instance_id:number;
  reference_entity:string;
  target_entity:string;
  datasource_type:string;
  db_host:string;
  db_port:number;
  service_id:string;
  ons_nodes:string;
  status:string;
  requested_by:string;
  azure_pipeline_id?:number|null;
  azure_run_id?:number|null;
  azure_run_url?:string|null;
  preview?:DatasourcePlan|null;
  result_message?:string|null;
  created_at:string;
  updated_at:string;
  completed_at?:string|null;
}
