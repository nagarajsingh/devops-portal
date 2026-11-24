export type Role = "developer" | "devops";
export type PageKey = "home"|"dashboard"|"requests"|"file-placement"|"monitoring"|"kubernetes-logs"|"deployment-management"|"ms-portal"|"devops-tasks"|"datasources"|"inventory"|"profile"|"admin";
export interface NavItem { key:PageKey; label:string; devopsOnly?:boolean; adminOnly?:boolean; href?:string; }
export interface AuthSession { access_token:string; token_type:string; username:string; role:Role; is_admin:boolean; }
export interface PortalUser { id:number; email:string; role:Role; is_admin:boolean; is_active:boolean; created_at:string; updated_at:string; }
export type DevOpsTaskStatus="backlog"|"inprogress"|"completed";
export type DevOpsTaskPriority="low"|"medium"|"high"|"critical";
export interface DevOpsTaskComment{id:string;author:string;text:string;created_at:string;}
export interface DevOpsTask{id:string;title:string;description:string;assignee:string;status:DevOpsTaskStatus;priority:DevOpsTaskPriority;created_by:string;created_at:string;updated_at:string;comments:DevOpsTaskComment[];history:{at:string;actor:string;action:string}[];}
export type ApplicationType="H2H"|"Collections"|"Native-Mobile"|"Safenet";
export interface DatabaseCreationRequest { environment:string; db_username:string; server_url:string; server_port:number|null; db_name:string; }
export interface PipelineRequestInput { application_type:ApplicationType; app_owner:string; repository_name:string; reference_repository_name:string; reference_branch?:string; setup_pipeline:boolean; update_values:boolean; pipeline_type?:string; ingress_path:string; ingress_name?:string; create_service:boolean; service_name:string; service_port:number; namespace:string; target_cluster:string; acl_details:string; database_requests:DatabaseCreationRequest[]; comments?:string; }
export interface KubernetesService {name:string;ports:number[];} export interface KubernetesTarget{name:string;mode:"direct"|"azure_pipeline";}
export interface ProvisionStep {status:string;message?:string;id?:string;run_id?:number;url?:string;branch?:string;source_branch?:string;files?:string[];name?:string;yaml_path?:string;target_cluster?:string;requires_confirmation?:boolean;confirmation_action?:string;}
export interface TimelineEvent{at:string;action:string;actor:string;detail?:string;}
export interface PipelineRequest extends PipelineRequestInput{id:string;requested_by:string;status:string;created_at:string;updated_at?:string;reviewed_by?:string;review_comments?:string;closure_comment?:string;closure_mail_sent?:boolean|null;app_owner_decision_by?:string;app_owner_decision_at?:string;app_owner_comment?:string;original_request?:PipelineRequestInput;provisioning?:Record<string,ProvisionStep>;timeline?:TimelineEvent[];}
export interface ReviewUpdate extends PipelineRequestInput{review_comments?:string;}


export interface DatasourceApplication {
  id:number;
  code:string;
  display_name:string;
  is_active:boolean;
}

export interface DatasourceEntityProfile {
  id:number;
  entity_code:string;
  service_id:string;
  schema_username:string;
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
  inventory_hostname:string;
  base_path:string;
  domain_name:string;
  admin_host:string;
  admin_port:number;
  ssh_port:number;
  wlst_path:string;
  artifacts_location:string;
  common_artifacts_location:string;
  cz_config_location:string;
  ear_path:string;
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
  password_source:"database_encrypted";
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
  change_type?:"Create"|"Update";
  missing_targets?:string[];
}

export interface DatasourcePlanSummary {
  total:number;
  created_count:number;
  created_names:string[];
  updated_count?:number;
  updated_names?:string[];
  ready_count:number;
}

export interface DatasourcePlan {
  request_id:string;
  application:string;
  environment:string;
  domain_name:string;
  action:string;
  operation_mode?:"create"|"update";
  datasource_name?:string;
  datasource_type:string;
  reference_entity:string;
  target_entity:string;
  datasources:DatasourcePlanItem[];
  summary?:DatasourcePlanSummary;
}

export interface DatasourceOperation {
  id:number;
  request_id:string;
  environment_instance_id:number;
  reference_entity:string;
  target_entity:string;
  operation_mode:"create"|"update";
  datasource_name:string;
  target_targets:string[];
  datasource_type:string;
  db_host:string;
  db_port:number;
  service_id:string;
  schema_username:string;
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


export type InventoryCategory = "GTB" | "MICROSERVICES";

export interface InventoryCategorySummary {
  category: InventoryCategory;
  application_count: number;
  record_count: number;
  environment_count: number;
}

export interface InventorySummary {
  categories: InventoryCategorySummary[];
}

export interface InventoryApplication {
  id: number;
  category: InventoryCategory;
  code: string;
  display_name: string;
  is_active: boolean;
  record_count: number;
  environment_count: number;
  created_at: string;
  updated_at: string;
}

export interface InventoryEnvironment {
  id: number;
  code: string;
  display_name: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface InventoryRecord {
  id: number;
  application_id: number;
  application_code: string;
  application_name: string;
  category: InventoryCategory;
  environment_id: number;
  environment_code: string;
  environment_name: string;
  ip_address: string;
  hostname: string;
  asset_type: string;
  app_name: string;
  ssh_username: string;
  ssh_password_configured: boolean;
  application_username: string;
  application_password_configured: boolean;
  console_details: string;
  notes: string;
  is_active: boolean;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}


export interface InventoryHistoryEvent {
  id:number;
  entity_type:string;
  entity_id:number|null;
  entity_name:string;
  action:string;
  field_name:string;
  old_value:string|null;
  new_value:string|null;
  actor:string;
  source:string;
  created_at:string;
}

export interface InventoryAudit {
  id: number;
  inventory_record_id: number | null;
  action: string;
  actor: string;
  detail: string;
  created_at: string;
}


export interface InventoryImportPreviewRow {
  source_row:number;
  environment:string;
  ip_address:string;
  hostname:string;
  application:string;
  asset_type:string;
  app_name:string;
  ssh_username:string;
  ssh_password_configured:boolean;
  application_username:string;
  application_password_configured:boolean;
  console_details:string;
  notes:string;
  warnings:string[];
}

export interface InventoryImportPreview {
  file_sha256:string;
  sheet_name:string;
  header_row:number;
  total_rows:number;
  ready_rows:number;
  invalid_rows:number;
  application_count:number;
  environment_count:number;
  applications:string[];
  environments:string[];
  warning_count:number;
  warnings:string[];
  preview_rows:InventoryImportPreviewRow[];
  preview_truncated:boolean;
}

export interface InventoryImportResult {
  file_sha256:string;
  sheet_name:string;
  total_rows:number;
  created_count:number;
  updated_count:number;
  skipped_count:number;
  created_applications:string[];
  created_environments:string[];
  errors:string[];
}


export interface InventoryMsGroup {
  id:number;
  code:string;
  display_name:string;
  is_active:boolean;
  service_count:number;
  configuration_count:number;
  environment_count:number;
  created_at:string;
  updated_at:string;
}

export interface InventoryMsService {
  id:number;
  group_id:number;
  group_code:string;
  group_name:string;
  code:string;
  display_name:string;
  is_active:boolean;
  configuration_count:number;
  environment_count:number;
  created_at:string;
  updated_at:string;
}

export interface InventoryMsConfiguration {
  id:number;
  group_id:number;
  group_code:string;
  group_name:string;
  service_id:number;
  service_code:string;
  service_name:string;
  environment_id:number;
  environment_code:string;
  environment_name:string;
  connection_name:string;
  db_url:string;
  db_name:string;
  db_username:string;
  db_password_configured:boolean;
  notes:string;
  is_active:boolean;
  created_by:string;
  updated_by:string;
  created_at:string;
  updated_at:string;
}

export interface InventoryMsImportPreviewRow {
  source_row:number;
  group:string;
  service:string;
  environment:string;
  connection_name:string;
  db_url:string;
  db_name:string;
  db_username:string;
  db_password_configured:boolean;
  notes:string;
  warnings:string[];
}

export interface InventoryMsImportPreview {
  file_sha256:string;
  sheet_name:string;
  header_row:number;
  total_rows:number;
  ready_rows:number;
  invalid_rows:number;
  group_count:number;
  service_count:number;
  environment_count:number;
  groups:string[];
  services:string[];
  environments:string[];
  warning_count:number;
  warnings:string[];
  preview_rows:InventoryMsImportPreviewRow[];
  preview_truncated:boolean;
}

export interface InventoryMsImportResult {
  file_sha256:string;
  sheet_name:string;
  total_rows:number;
  created_count:number;
  updated_count:number;
  skipped_count:number;
  created_groups:string[];
  created_services:string[];
  created_environments:string[];
  errors:string[];
}


export type InventoryPatchEnvironmentClass="NON_PROD"|"PROD"|"DR";
export type InventoryPatchStatus="NOT_STARTED"|"SCHEDULED"|"IN_PROGRESS"|"COMPLETED"|"BLOCKED";

export interface InventoryPatchActivity {
  id:number;
  cycle_id:number;
  cycle_code:string;
  previous_patched_date:string;
  planned_date:string;
  status:InventoryPatchStatus;
  app_team_approval:string;
  cr_number:string;
  comments:string;
  patch_role:string;
  updated_by:string;
  updated_at:string;
}

export interface InventoryPatchingAsset {
  id:number;
  source_type:"GTB"|"MANUAL"|"IMPORT"|string;
  source_id:number|null;
  asset_identifier:string;
  hostname:string;
  application:string;
  application_owner:string;
  asset_type:string;
  environment_name:string;
  environment_class:InventoryPatchEnvironmentClass;
  is_active:boolean;
  activity:InventoryPatchActivity|null;
  created_by:string;
  updated_by:string;
  created_at:string;
  updated_at:string;
}

export interface InventoryPatchCycle {
  id:number;
  code:string;
  quarter:number;
  year:number;
  start_date:string;
  end_date:string;
  is_active:boolean;
}

export interface InventoryPatchingSummary {
  total_assets:number;
  environment_counts:Record<InventoryPatchEnvironmentClass,number>;
  status_counts:Record<InventoryPatchStatus,number>;
}

export interface InventoryPatchingImportPreviewRow {
  source_row:number;
  environment_class:InventoryPatchEnvironmentClass;
  environment_name:string;
  asset_identifier:string;
  hostname:string;
  application:string;
  application_owner:string;
  asset_type:string;
  previous_patched_date:string;
  planned_date:string;
  status:string;
  app_team_approval:string;
  cr_number:string;
  comments:string;
  patch_role:string;
  warnings:string[];
}

export interface InventoryPatchingImportPreview {
  file_sha256:string;
  sheet_name:string;
  cycle_code:string;
  total_rows:number;
  environment_counts:Record<string,number>;
  status_counts:Record<string,number>;
  warning_count:number;
  warnings:string[];
  preview_rows:InventoryPatchingImportPreviewRow[];
  preview_truncated:boolean;
}

export interface InventoryPatchingImportResult {
  file_sha256:string;
  sheet_name:string;
  total_rows:number;
  cycle_id:number;
  cycle_code:string;
  created_assets:number;
  updated_assets:number;
  updated_activities:number;
  errors:string[];
}

export interface InventorySearchResult {
  query:string;
  total:number;
  gtb:Array<{
    id:number;
    application_id:number;
    application:string;
    environment:string;
    ip_address:string;
    hostname:string;
    asset_type:string;
    app_name:string;
    ssh_username:string;
    application_username:string;
    console_details:string;
    notes:string;
  }>;
  microservices:Array<{
    id:number;
    group_id:number;
    group:string;
    service_id:number;
    service:string;
    environment:string;
    connection_name:string;
    db_url:string;
    db_name:string;
    db_username:string;
  }>;
  patching:Array<{
    id:number;
    asset_identifier:string;
    hostname:string;
    application:string;
    application_owner:string;
    asset_type:string;
    environment_name:string;
    environment_class:InventoryPatchEnvironmentClass;
    source_type:string;
    status:InventoryPatchStatus;
    cr_number:string;
    planned_date:string;
    comments:string;
  }>;
}
