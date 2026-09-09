import type { ApplicationType, AuthSession, DevOpsTask, DevOpsTaskPriority, DevOpsTaskStatus, KubernetesService, KubernetesTarget, PipelineRequest, PipelineRequestInput, PortalUser, ReviewUpdate, Role } from "../types";
const API_BASE="/devops-portal/api";
export class ApiError extends Error{code?:string;status?:number;payload?:unknown;constructor(message:string,options:{code?:string;status?:number;payload?:unknown}={}){super(message);this.name="ApiError";Object.assign(this,options);}}
async function request<T>(path:string,options:RequestInit={},token?:string):Promise<T>{const response=await fetch(`${API_BASE}${path}`,{...options,headers:{"Content-Type":"application/json",...(token?{Authorization:`Bearer ${token}`}:{}) ,...options.headers}});if(!response.ok){const body=await response.json().catch(()=>({detail:"Request failed"}));const d=body?.detail;throw new ApiError(typeof d==="string"?d:d?.message??"Request failed",{code:typeof d==="object"&&d?d.code:undefined,status:response.status,payload:d});}if(response.status===204)return undefined as T;return response.json() as Promise<T>;}
export const login=(username:string,password:string,role:Role)=>request<AuthSession>("/auth/login",{method:"POST",body:JSON.stringify({username,password,role})});
export const getPortalUsers=(token:string)=>request<PortalUser[]>("/admin/users",{},token);
export const createPortalUser=(payload:{email:string;password:string;role:Role;is_admin:boolean},token:string)=>request<PortalUser>("/admin/users",{method:"POST",body:JSON.stringify(payload)},token);
export const updatePortalUser=(id:number,payload:{role:Role;is_admin:boolean;is_active:boolean;password?:string},token:string)=>request<PortalUser>(`/admin/users/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const deletePortalUser=(id:number,token:string)=>request<void>(`/admin/users/${id}`,{method:"DELETE"},token);
export const getDevOpsTaskAssignees=(token:string)=>request<{email:string;is_admin:boolean}[]>("/devops-tasks/assignees",{},token);
export const getDevOpsTasks=(token:string,filters:Record<string,string>={})=>{const q=new URLSearchParams(Object.entries(filters).filter(([,v])=>v));return request<DevOpsTask[]>(`/devops-tasks?${q}`,{},token)};
export const createDevOpsTask=(p:{title:string;description:string;assignee:string;priority:DevOpsTaskPriority},token:string)=>request<DevOpsTask>("/devops-tasks",{method:"POST",body:JSON.stringify(p)},token);
export const updateDevOpsTask=(id:string,p:{title?:string;description?:string;status?:DevOpsTaskStatus;priority?:DevOpsTaskPriority},token:string)=>request<DevOpsTask>(`/devops-tasks/${id}`,{method:"PUT",body:JSON.stringify(p)},token);
export const reassignDevOpsTask=(id:string,assignee:string,token:string)=>request<DevOpsTask>(`/devops-tasks/${id}/reassign`,{method:"POST",body:JSON.stringify({assignee})},token);
export const commentDevOpsTask=(id:string,text:string,token:string)=>request<DevOpsTask>(`/devops-tasks/${id}/comments`,{method:"POST",body:JSON.stringify({text})},token);
export const getApplicationOwners=(token:string)=>request<Record<ApplicationType,string>>("/configuration/app-owners",{},token);
export const getKubernetesTargets=(token:string)=>request<KubernetesTarget[]>("/configuration/kubernetes-targets",{},token);
export const getNamespaces=(token:string,targetCluster="local-cluster")=>request<string[]>(`/namespaces/${encodeURIComponent(targetCluster)}`,{},token);
export const getIngresses=(namespace:string,token:string,targetCluster="local-cluster")=>request<string[]>(`/ingresses/${encodeURIComponent(targetCluster)}/${encodeURIComponent(namespace)}`,{},token);
export const getServices=(namespace:string,token:string,targetCluster="local-cluster")=>request<KubernetesService[]>(`/services/${encodeURIComponent(targetCluster)}/${encodeURIComponent(namespace)}`,{},token);
export const createPipelineRequest=(payload:PipelineRequestInput,token:string)=>request<PipelineRequest>("/requests",{method:"POST",body:JSON.stringify(payload)},token);
export const getPipelineRequests=(token:string)=>request<PipelineRequest[]>("/requests",{},token);
export const updatePipelineRequest=(id:string,payload:ReviewUpdate,token:string)=>request<PipelineRequest>(`/requests/${id}`,{method:"PUT",body:JSON.stringify(payload)},token);
export const approvePipelineRequest=(id:string,pat:string,token:string)=>request<PipelineRequest>(`/requests/${id}/approve`,{method:"POST",body:JSON.stringify({azure_devops_pat:pat})},token);
export const confirmExistingRepository=(id:string,pat:string,token:string)=>request<PipelineRequest>(`/requests/${id}/confirm-existing-repository`,{method:"POST",body:JSON.stringify({azure_devops_pat:pat})},token);
export const rejectPipelineRequest=(id:string,reason:string,token:string)=>request<PipelineRequest>(`/requests/${id}/reject`,{method:"POST",body:JSON.stringify({reason})},token);
export const closePipelineRequest=(id:string,comment:string,token:string)=>request<PipelineRequest>(`/requests/${id}/close`,{method:"POST",body:JSON.stringify({comment})},token);
