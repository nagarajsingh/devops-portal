import type { ApplicationType, AuthSession, DatasourceApplication, DatasourceOperation, DevOpsTask, DevOpsTaskPriority, DevOpsTaskStatus, InventoryApplication, InventoryAudit, InventoryCategory, InventoryEnvironment, InventoryHistoryEvent, InventoryImportPreview, InventoryImportResult, InventoryMsConfiguration, InventoryMsGroup, InventoryMsImportPreview, InventoryMsImportResult, InventoryMsService, InventoryPatchCycle, InventoryPatchingAsset, InventoryPatchingImportPreview, InventoryPatchingImportResult, InventoryPatchingSummary, InventoryRecord, InventorySearchResult, InventorySummary, KubernetesService, KubernetesTarget, PipelineRequest, PipelineRequestInput, PortalUser, ReviewUpdate, Role, WebLogicEnvironment } from "../types";
const API_BASE="/devops-portal/api";
export class ApiError extends Error{code?:string;status?:number;payload?:unknown;constructor(message:string,options:{code?:string;status?:number;payload?:unknown}={}){super(message);this.name="ApiError";Object.assign(this,options);}}
async function request<T>(path:string,options:RequestInit={},token?:string):Promise<T>{const response=await fetch(`${API_BASE}${path}`,{...options,headers:{"Content-Type":"application/json",...(token?{Authorization:`Bearer ${token}`}:{}) ,...options.headers}});if(!response.ok){const body=await response.json().catch(()=>({detail:"Request failed"}));const d=body?.detail;throw new ApiError(typeof d==="string"?d:d?.message??"Request failed",{code:typeof d==="object"&&d?d.code:undefined,status:response.status,payload:d});}if(response.status===204)return undefined as T;return response.json() as Promise<T>;}
export type FilePlacementPod={name:string;phase:string;containers:string[]};
export type FilePlacementAudit={id:number;user_email:string;user_role:string;file_name:string;file_size:number;sha256?:string|null;namespace:string;pod_name:string;container_name:string;destination_path:string;status:string;detail?:string|null;created_at:string};
export const login=(username:string,password:string)=>request<AuthSession>("/auth/login",{method:"POST",body:JSON.stringify({username,password})});
export const changePassword=(payload:{current_password:string;new_password:string;confirm_password:string},token:string)=>request<{message:string}>("/auth/change-password",{method:"POST",body:JSON.stringify(payload)},token);
export const getPortalUsers=(token:string)=>request<PortalUser[]>("/admin/users",{},token);
export const createPortalUser=(payload:{email:string;password:string;role:Role;is_admin:boolean},token:string)=>request<PortalUser>("/admin/users",{method:"POST",body:JSON.stringify(payload)},token);
export const updatePortalUser=(id:number,payload:{role:Role;is_admin:boolean;is_active:boolean;password?:string},token:string)=>request<PortalUser>(`/admin/users/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const resetPortalUserPassword=(id:number,payload:{new_password:string;confirm_password:string},token:string)=>request<PortalUser>(`/admin/users/${id}/reset-password`,{method:"POST",body:JSON.stringify(payload)},token);
export const deletePortalUser=(id:number,token:string)=>request<void>(`/admin/users/${id}`,{method:"DELETE"},token);
export const getDevOpsTaskAssignees=(token:string)=>request<{email:string;is_admin:boolean}[]>("/devops-tasks/assignees",{},token);
export const getDevOpsTasks=(token:string,filters:Record<string,string>={})=>{const q=new URLSearchParams(Object.entries(filters).filter(([,v])=>v));return request<DevOpsTask[]>(`/devops-tasks?${q}`,{},token)};
export const createDevOpsTask=(p:{title:string;description:string;assignee:string;priority:DevOpsTaskPriority},token:string)=>request<DevOpsTask>("/devops-tasks",{method:"POST",body:JSON.stringify(p)},token);
export const updateDevOpsTask=(id:string,p:{title?:string;description?:string;status?:DevOpsTaskStatus;priority?:DevOpsTaskPriority},token:string)=>request<DevOpsTask>(`/devops-tasks/${id}`,{method:"PUT",body:JSON.stringify(p)},token);
export const reassignDevOpsTask=(id:string,assignee:string,token:string)=>request<DevOpsTask>(`/devops-tasks/${id}/reassign`,{method:"POST",body:JSON.stringify({assignee})},token);
export const commentDevOpsTask=(id:string,text:string,token:string)=>request<DevOpsTask>(`/devops-tasks/${id}/comments`,{method:"POST",body:JSON.stringify({text})},token);
export const getFilePlacementNamespaces=(token:string)=>request<string[]>("/file-placement/namespaces",{},token);
export const getFilePlacementPods=(namespace:string,token:string)=>request<FilePlacementPod[]>(`/file-placement/pods/${encodeURIComponent(namespace)}`,{},token);
export const getFilePlacementAudit=(token:string,limit=25)=>request<FilePlacementAudit[]>(`/file-placement/audit?limit=${limit}`,{},token);
export async function uploadFilePlacement(payload:{file:File;namespace:string;podName:string;containerName?:string;destinationPath:string},token:string):Promise<FilePlacementAudit>{const form=new FormData();form.append("upload",payload.file);form.append("namespace",payload.namespace);form.append("pod_name",payload.podName);form.append("container_name",payload.containerName??"");form.append("destination_path",payload.destinationPath);const response=await fetch(`${API_BASE}/file-placement/upload`,{method:"POST",headers:{Authorization:`Bearer ${token}`},body:form});if(!response.ok){const body=await response.json().catch(()=>({detail:"File placement failed"}));const detail=body?.detail;throw new ApiError(typeof detail==="string"?detail:"File placement failed",{status:response.status,payload:detail});}return response.json() as Promise<FilePlacementAudit>}
export const getApplicationOwners=(token:string)=>request<Record<ApplicationType,string>>("/configuration/app-owners",{},token);
export const getKubernetesTargets=(token:string)=>request<KubernetesTarget[]>("/configuration/kubernetes-targets",{},token);
export const getNamespaces=(token:string,targetCluster="local-cluster")=>request<string[]>(`/namespaces/${encodeURIComponent(targetCluster)}`,{},token);
export const getIngresses=(namespace:string,token:string,targetCluster="local-cluster")=>request<string[]>(`/ingresses/${encodeURIComponent(targetCluster)}/${encodeURIComponent(namespace)}`,{},token);
export const getServices=(namespace:string,token:string,targetCluster="local-cluster")=>request<KubernetesService[]>(`/services/${encodeURIComponent(targetCluster)}/${encodeURIComponent(namespace)}`,{},token);
export const createPipelineRequest=(payload:PipelineRequestInput,token:string)=>request<PipelineRequest>("/requests",{method:"POST",body:JSON.stringify(payload)},token);
export const getPipelineRequests=(token:string)=>request<PipelineRequest[]>("/requests",{},token);
export const updatePipelineRequest=(id:string,payload:ReviewUpdate,token:string)=>request<PipelineRequest>(`/requests/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const approvePipelineRequest=(id:string,pat:string,token:string)=>request<PipelineRequest>(`/requests/${id}/approve`,{method:"POST",body:JSON.stringify({azure_devops_pat:pat})},token);
export const provisionRemoteKubernetes=(id:string,pat:string,token:string)=>request<PipelineRequest>(`/requests/${id}/provision-remote-kubernetes`,{method:"POST",body:JSON.stringify({azure_devops_pat:pat})},token);
export const confirmExistingRepository=(id:string,pat:string,token:string)=>request<PipelineRequest>(`/requests/${id}/confirm-existing-repository`,{method:"POST",body:JSON.stringify({azure_devops_pat:pat})},token);
export const confirmExistingBuildPipeline=(id:string,pat:string,token:string)=>request<PipelineRequest>(`/requests/${id}/confirm-existing-build-pipeline`,{method:"POST",body:JSON.stringify({azure_devops_pat:pat})},token);
export const rejectPipelineRequest=(id:string,reason:string,token:string)=>request<PipelineRequest>(`/requests/${id}/reject`,{method:"POST",body:JSON.stringify({reason})},token);
export const closePipelineRequest=(id:string,comment:string,databaseCredentials:{request_index:number;password:string}[],token:string)=>request<PipelineRequest>(`/requests/${id}/close`,{method:"POST",body:JSON.stringify({comment,database_credentials:databaseCredentials})},token);


export type WebLogicEnvironmentInput={
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
  agent_pool:string;
  default_db_host:string;
  default_db_port:number;
  default_ons_nodes:string;
  weblogic_username:string;
  weblogic_password?:string;
  ssh_username:string;
  ssh_password?:string;
  is_production:boolean;
  is_active:boolean;
};

export type DatasourceEntityInput={
  service_id:string;
  schema_username:string;
  db_host:string;
  db_port:number;
  ons_nodes:string;
  password_pattern?:string;
};

export type DatasourcePreviewInput={
  environment_instance_id:number;
  operation_mode:"create"|"update";
  reference_entity:string;
  target_entity:string;
  datasource_name:string;
  target_targets:string[];
  datasource_type:"standalone"|"gridlink";
  db_host:string;
  db_port:number;
  service_id:string;
  schema_username:string;
  password_pattern?:string;
  explicit_password?:string;
  ons_nodes:string;
  azure_devops_pat:string;
};

export const getDatasourceApplications=(token:string)=>request<DatasourceApplication[]>("/datasources/applications",{},token);
export const getDatasourceEnvironments=(token:string)=>request<WebLogicEnvironment[]>("/datasources/environments",{},token);
export const createDatasourceEnvironment=(payload:WebLogicEnvironmentInput,token:string)=>request<WebLogicEnvironment>("/datasources/environments",{method:"POST",body:JSON.stringify(payload)},token);
export const updateDatasourceEnvironment=(id:number,payload:WebLogicEnvironmentInput,token:string)=>request<WebLogicEnvironment>(`/datasources/environments/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const saveDatasourceEntityProfile=(environmentId:number,entityCode:string,payload:DatasourceEntityInput,token:string)=>request<import("../types").DatasourceEntityProfile>(`/datasources/environments/${environmentId}/entities/${encodeURIComponent(entityCode)}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const getDatasourceOperations=(token:string,limit=50)=>request<DatasourceOperation[]>(`/datasources/operations?limit=${limit}`,{},token);
export const previewDatasources=(payload:DatasourcePreviewInput,token:string)=>request<DatasourceOperation>("/datasources/preview",{method:"POST",body:JSON.stringify(payload)},token);
export const applyDatasourceOperation=(id:number,pat:string,token:string)=>request<DatasourceOperation>(`/datasources/operations/${id}/apply`,{method:"POST",body:JSON.stringify({azure_devops_pat:pat})},token);


export type InventoryRecordInput = {
  application_id:number;
  environment_id:number;
  ip_address:string;
  hostname:string;
  asset_type:string;
  app_name:string;
  ssh_username:string;
  ssh_password?:string;
  application_username:string;
  application_password?:string;
  console_details:string;
  notes:string;
};

export const getInventorySummary=(token:string)=>request<InventorySummary>("/inventory/summary",{},token);
export const getInventoryApplications=(category:InventoryCategory,token:string,includeInactive=false)=>request<InventoryApplication[]>(`/inventory/applications?category=${encodeURIComponent(category)}${includeInactive?"&include_inactive=true":""}`,{},token);
export const createInventoryApplication=(payload:{category:InventoryCategory;code:string;display_name:string},token:string)=>request<InventoryApplication>("/inventory/applications",{method:"POST",body:JSON.stringify(payload)},token);
export const updateInventoryApplication=(id:number,payload:{category:InventoryCategory;code:string;display_name:string},token:string)=>request<InventoryApplication>(`/inventory/applications/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const archiveInventoryApplication=(id:number,token:string)=>request<InventoryApplication>(`/inventory/applications/${id}`,{method:"DELETE"},token);
export const restoreInventoryApplication=(id:number,token:string)=>request<InventoryApplication>(`/inventory/applications/${id}/restore`,{method:"POST"},token);
export const getInventoryEnvironments=(token:string,category:InventoryCategory="GTB",includeInactive=false)=>{const p=new URLSearchParams({category});if(includeInactive)p.set("include_inactive","true");return request<InventoryEnvironment[]>(`/inventory/environments?${p.toString()}`,{},token);};
export const createInventoryEnvironment=(payload:{category:InventoryCategory;code:string;display_name:string},token:string)=>request<InventoryEnvironment>("/inventory/environments",{method:"POST",body:JSON.stringify(payload)},token);
export const updateInventoryEnvironment=(id:number,payload:{category:InventoryCategory;code:string;display_name:string},token:string)=>request<InventoryEnvironment>(`/inventory/environments/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const archiveInventoryEnvironment=(id:number,category:InventoryCategory,token:string)=>request<InventoryEnvironment>(`/inventory/environments/${id}?category=${encodeURIComponent(category)}`,{method:"DELETE"},token);
export const restoreInventoryEnvironment=(id:number,category:InventoryCategory,token:string)=>request<InventoryEnvironment>(`/inventory/environments/${id}/restore?category=${encodeURIComponent(category)}`,{method:"POST"},token);
export const getInventoryRecords=(token:string,filters:{application_id?:number;environment_id?:number;q?:string}={})=>{const query=new URLSearchParams();if(filters.application_id)query.set("application_id",String(filters.application_id));if(filters.environment_id)query.set("environment_id",String(filters.environment_id));if(filters.q)query.set("q",filters.q);const suffix=query.toString();return request<InventoryRecord[]>(`/inventory/records${suffix?`?${suffix}`:""}`,{},token);};
export const createInventoryRecord=(payload:InventoryRecordInput,token:string)=>request<InventoryRecord>("/inventory/records",{method:"POST",body:JSON.stringify(payload)},token);
export const updateInventoryRecord=(id:number,payload:InventoryRecordInput,token:string)=>request<InventoryRecord>(`/inventory/records/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const deleteInventoryRecord=(id:number,token:string)=>request<void>(`/inventory/records/${id}`,{method:"DELETE"},token);
export const revealInventoryCredential=(id:number,type:"SSH"|"APPLICATION",token:string)=>request<{password:string}>(`/inventory/records/${id}/credentials/${type}/reveal`,{method:"POST"},token);
export const getInventoryAudit=(token:string,limit=100)=>request<InventoryAudit[]>(`/inventory/audit?limit=${limit}`,{},token);
export const getInventoryHistory=(token:string,filters:{entity_type?:string;entity_id?:number;actor?:string;action?:string;q?:string;limit?:number}={})=>{const p=new URLSearchParams();Object.entries(filters).forEach(([k,v])=>{if(v!==undefined&&v!==null&&v!=="")p.set(k,String(v));});const s=p.toString();return request<InventoryHistoryEvent[]>(`/inventory/history${s?`?${s}`:""}`,{},token);};


async function uploadInventoryWorkbook<T>(path:string,file:File,token:string):Promise<T>{
  const form=new FormData();
  form.append("upload",file);
  const response=await fetch(`${API_BASE}${path}`,{
    method:"POST",
    headers:{Authorization:`Bearer ${token}`},
    body:form,
  });
  if(!response.ok){
    const body=await response.json().catch(()=>({detail:"Inventory import failed"}));
    const detail=body?.detail;
    throw new ApiError(typeof detail==="string"?detail:"Inventory import failed",{status:response.status,payload:detail});
  }
  return response.json() as Promise<T>;
}

export const previewInventoryExcel=(file:File,token:string)=>uploadInventoryWorkbook<InventoryImportPreview>("/inventory/import/preview",file,token);
export const commitInventoryExcel=(file:File,token:string)=>uploadInventoryWorkbook<InventoryImportResult>("/inventory/import/commit",file,token);


export type InventoryMsConfigurationInput={
  service_id:number;
  environment_id:number;
  connection_name:string;
  db_url:string;
  db_name:string;
  db_username:string;
  db_password?:string;
  notes:string;
};

export const getInventoryMsGroups=(token:string,includeInactive=false)=>request<InventoryMsGroup[]>(`/inventory/microservices/groups${includeInactive?"?include_inactive=true":""}`,{},token);
export const createInventoryMsGroup=(payload:{code:string;display_name:string},token:string)=>request<InventoryMsGroup>("/inventory/microservices/groups",{method:"POST",body:JSON.stringify(payload)},token);
export const updateInventoryMsGroup=(id:number,payload:{code:string;display_name:string},token:string)=>request<InventoryMsGroup>(`/inventory/microservices/groups/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const archiveInventoryMsGroup=(id:number,token:string)=>request<InventoryMsGroup>(`/inventory/microservices/groups/${id}`,{method:"DELETE"},token);
export const restoreInventoryMsGroup=(id:number,token:string)=>request<InventoryMsGroup>(`/inventory/microservices/groups/${id}/restore`,{method:"POST"},token);
export const getInventoryMsServices=(token:string,groupId?:number,q="",includeInactive=false)=>{const p=new URLSearchParams();if(groupId)p.set("group_id",String(groupId));if(q)p.set("q",q);if(includeInactive)p.set("include_inactive","true");const s=p.toString();return request<InventoryMsService[]>(`/inventory/microservices/services${s?`?${s}`:""}`,{},token);};
export const createInventoryMsService=(payload:{group_id:number;code:string;display_name:string},token:string)=>request<InventoryMsService>("/inventory/microservices/services",{method:"POST",body:JSON.stringify(payload)},token);
export const updateInventoryMsService=(id:number,payload:{group_id:number;code:string;display_name:string},token:string)=>request<InventoryMsService>(`/inventory/microservices/services/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const archiveInventoryMsService=(id:number,token:string)=>request<InventoryMsService>(`/inventory/microservices/services/${id}`,{method:"DELETE"},token);
export const restoreInventoryMsService=(id:number,token:string)=>request<InventoryMsService>(`/inventory/microservices/services/${id}/restore`,{method:"POST"},token);
export const getInventoryMsConfigurations=(token:string,filters:{service_id?:number;environment_id?:number;q?:string}={})=>{const p=new URLSearchParams();if(filters.service_id)p.set("service_id",String(filters.service_id));if(filters.environment_id)p.set("environment_id",String(filters.environment_id));if(filters.q)p.set("q",filters.q);const s=p.toString();return request<InventoryMsConfiguration[]>(`/inventory/microservices/configurations${s?`?${s}`:""}`,{},token);};
export const createInventoryMsConfiguration=(payload:InventoryMsConfigurationInput,token:string)=>request<InventoryMsConfiguration>("/inventory/microservices/configurations",{method:"POST",body:JSON.stringify(payload)},token);
export const updateInventoryMsConfiguration=(id:number,payload:InventoryMsConfigurationInput,token:string)=>request<InventoryMsConfiguration>(`/inventory/microservices/configurations/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const deleteInventoryMsConfiguration=(id:number,token:string)=>request<void>(`/inventory/microservices/configurations/${id}`,{method:"DELETE"},token);
export const revealInventoryMsPassword=(id:number,token:string)=>request<{password:string}>(`/inventory/microservices/configurations/${id}/credential/reveal`,{method:"POST"},token);
export const previewInventoryMsExcel=(file:File,token:string)=>uploadInventoryWorkbook<InventoryMsImportPreview>("/inventory/microservices/import/preview",file,token);
export const commitInventoryMsExcel=(file:File,token:string)=>uploadInventoryWorkbook<InventoryMsImportResult>("/inventory/microservices/import/commit",file,token);

export async function downloadInventoryExport(
  kind:"gtb"|"microservices"|"patching",
  format:"xlsx"|"pdf",
  token:string,
  filters:{application_id?:number;group_id?:number;service_id?:number;environment_id?:number;cycle_id?:number;environment_class?:string;status?:string}={}
){
  const query=new URLSearchParams();
  Object.entries(filters).forEach(([key,value])=>{if(value)query.set(key,String(value));});
  const suffix=query.toString();
  const response=await fetch(`${API_BASE}/inventory/export/${kind}.${format}${suffix?`?${suffix}`:""}`,{headers:{Authorization:`Bearer ${token}`}});
  if(!response.ok){
    const body=await response.json().catch(()=>({detail:"Inventory export failed"}));
    throw new ApiError(typeof body?.detail==="string"?body.detail:"Inventory export failed",{status:response.status,payload:body?.detail});
  }
  const blob=await response.blob();
  const disposition=response.headers.get("Content-Disposition")||"";
  const match=disposition.match(/filename="?([^";]+)"?/i);
  const filename=match?.[1]||`${kind}-inventory.${format}`;
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement("a");
  anchor.href=url;
  anchor.download=filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}


export type InventoryPatchingAssetInput={
  asset_identifier:string;
  hostname:string;
  application:string;
  application_owner:string;
  asset_type:string;
  environment_name:string;
  environment_class:"NON_PROD"|"PROD"|"DR";
};

export type InventoryPatchActivityInput={
  previous_patched_date?:string|null;
  planned_date?:string|null;
  status:"NOT_STARTED"|"SCHEDULED"|"IN_PROGRESS"|"COMPLETED"|"BLOCKED";
  app_team_approval:string;
  cr_number:string;
  comments:string;
  patch_role:string;
};

export const searchInventory=(q:string,token:string)=>request<InventorySearchResult>(`/inventory/search?q=${encodeURIComponent(q)}`,{},token);
export const getInventoryPatchCycles=(token:string)=>request<InventoryPatchCycle[]>("/inventory/patching/cycles",{},token);
export const createInventoryPatchCycle=(code:string,token:string)=>request<InventoryPatchCycle>("/inventory/patching/cycles",{method:"POST",body:JSON.stringify({code})},token);
export const getInventoryPatchingSummary=(token:string,cycleId?:number)=>request<InventoryPatchingSummary>(`/inventory/patching/summary${cycleId?`?cycle_id=${cycleId}`:""}`,{},token);
export const getInventoryPatchingAssets=(token:string,filters:{cycle_id?:number;environment_class?:string;status?:string;q?:string}={})=>{const p=new URLSearchParams();Object.entries(filters).forEach(([k,v])=>{if(v!==undefined&&v!==null&&v!=="")p.set(k,String(v));});const s=p.toString();return request<InventoryPatchingAsset[]>(`/inventory/patching/assets${s?`?${s}`:""}`,{},token);};
export const createInventoryPatchingAsset=(payload:InventoryPatchingAssetInput,token:string)=>request<InventoryPatchingAsset>("/inventory/patching/assets",{method:"POST",body:JSON.stringify(payload)},token);
export const updateInventoryPatchingAsset=(id:number,payload:InventoryPatchingAssetInput,token:string)=>request<InventoryPatchingAsset>(`/inventory/patching/assets/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const deleteInventoryPatchingAsset=(id:number,token:string)=>request<void>(`/inventory/patching/assets/${id}`,{method:"DELETE"},token);
export const saveInventoryPatchActivity=(assetId:number,cycleId:number,payload:InventoryPatchActivityInput,token:string)=>request<InventoryPatchingAsset>(`/inventory/patching/assets/${assetId}/cycles/${cycleId}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const previewInventoryPatchingExcel=(file:File,token:string)=>uploadInventoryWorkbook<InventoryPatchingImportPreview>("/inventory/patching/import/preview",file,token);
export const commitInventoryPatchingExcel=(file:File,token:string)=>uploadInventoryWorkbook<InventoryPatchingImportResult>("/inventory/patching/import/commit",file,token);
