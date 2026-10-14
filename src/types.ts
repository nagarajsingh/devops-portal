export type Role = "developer" | "devops";
export type PageKey = "home"|"dashboard"|"requests"|"file-placement"|"monitoring"|"deployment-management"|"ms-portal"|"devops-tasks"|"profile"|"admin";
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
export interface ProvisionStep {status:string;message?:string;id?:string;run_id?:number;url?:string;branch?:string;source_branch?:string;files?:string[];name?:string;yaml_path?:string;target_cluster?:string;}
export interface TimelineEvent{at:string;action:string;actor:string;detail?:string;}
export interface PipelineRequest extends PipelineRequestInput{id:string;requested_by:string;status:string;created_at:string;updated_at?:string;reviewed_by?:string;review_comments?:string;closure_comment?:string;app_owner_decision_by?:string;app_owner_decision_at?:string;app_owner_comment?:string;original_request?:PipelineRequestInput;provisioning?:Record<string,ProvisionStep>;timeline?:TimelineEvent[];}
export interface ReviewUpdate extends PipelineRequestInput{review_comments?:string;}
