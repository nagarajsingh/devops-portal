import { useEffect, useState } from "react";
import { CheckCircle2, FileText, GitPullRequest, Play, Rocket, UploadCloud } from "lucide-react";

const API_BASE = "/devops-portal/api";
const APP_TYPES = ["H2H", "Collections", "GTB-Applications", "Native-Mobile", "Safenet"];
const COLLECTIONS_COUNTRIES = ["UAE", "Egypt"];

type Step = { status: string; url?: string };
type CollectionsItem = {
  selected: boolean;
  service: string;
  image_tag: string;
  vendor_image: string;
  pipeline_name: string;
  country: string;
};
type DeploymentRequest = {
  id:string; application_type:string; application:string; branch_name:string; environment:string;
  country?:string; app_owner:string; repository:string; target_branch:string; build_pipeline:string; status:string;
  requested_by:string; created_at:string; document_name:string; extracted:boolean;
  war_files:string[]; jar_files:string[]; container_images:string[]; collections_items?:CollectionsItem[];
  steps:Record<string,Step>;
};

export default function DeploymentManagementPage({ token, role }: { token: string; role: string }) {
  const [file,setFile]=useState<File|null>(null);
  const [appType,setAppType]=useState("GTB-Applications");
  const [country,setCountry]=useState("UAE");
  const [appOwner,setAppOwner]=useState("");
  const [requests,setRequests]=useState<DeploymentRequest[]>([]);
  const [selected,setSelected]=useState<DeploymentRequest|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [pat,setPat]=useState("");

  async function loadRequests(){
    const r=await fetch(`${API_BASE}/deployment-management/requests`,{headers:{Authorization:`Bearer ${token}`}});
    if(r.ok){
      const rows=await r.json();
      setRequests(rows);
      if(selected)setSelected(rows.find((x:DeploymentRequest)=>x.id===selected.id)||selected);
    }
  }
  useEffect(()=>{void loadRequests()},[token]);

  async function submitDocument(){
    if(!file||!appOwner)return;
    setBusy(true);setMessage("");
    const form=new FormData();
    form.append("application_type",appType);
    form.append("app_owner",appOwner);
    if(appType==="Collections")form.append("country",country);
    form.append("document",file);
    try{
      const r=await fetch(`${API_BASE}/deployment-management/submit-document`,{method:"POST",headers:{Authorization:`Bearer ${token}`},body:form});
      const b=await r.json();
      setMessage(r.ok?`Request ${b.id} submitted for application-owner approval.`:b.detail||"Submission failed");
      if(r.ok){setFile(null);await loadRequests()}
    }catch(e){setMessage(e instanceof Error?e.message:"Submission failed")}finally{setBusy(false)}
  }

  async function action(id:string,name:string,updates:Record<string,unknown>={}){
    setBusy(true);setMessage("");
    try{
      const r=await fetch(`${API_BASE}/deployment-management/requests/${id}/${name}`,{
        method:"POST",
        headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},
        body:JSON.stringify({azure_devops_pat:pat||null,updates}),
      });
      const b=await r.json();
      setMessage(r.ok?`${name} completed for ${id}.`:b.detail||"Action failed");
      if(r.ok){setSelected(b);await loadRequests()}
    }catch(e){setMessage(e instanceof Error?e.message:"Action failed")}finally{setBusy(false)}
  }

  function updateSelected(key:keyof DeploymentRequest,value:unknown){if(selected)setSelected({...selected,[key]:value} as DeploymentRequest)}
  function updateCollectionItem(index:number,key:keyof CollectionsItem,value:string|boolean){
    if(!selected)return;
    const items=[...(selected.collections_items||[])];
    items[index]={...items[index],[key]:value};
    setSelected({...selected,collections_items:items});
  }
  const saveUpdates=()=>selected&&action(selected.id,"save-extracted-data",{
    application:selected.application,branch_name:selected.branch_name,environment:selected.environment,
    repository:selected.repository,target_branch:selected.target_branch,build_pipeline:selected.build_pipeline,
    war_files:selected.war_files,jar_files:selected.jar_files,container_images:selected.container_images,
    collections_items:selected.collections_items||[],
  });

  return <div className="deployment-management-page">
    <section className="deployment-hero"><div><span className="eyebrow">RELEASE ORCHESTRATION</span><h1>Deployment Management Dashboard</h1><p>Structured release documents, controlled approvals, code pull, pull requests, builds and deployments for five application architectures.</p></div><Rocket size={44}/></section>
    <div className="deployment-workflow">{["Document", "Owner approval", "DevOps extraction", "Code pull / PR", "Build", "Deployment"].map((x,i)=><div key={x}><span>{i+1}</span><strong>{x}</strong></div>)}</div>

    {role!=="devops"?
      <section className="deployment-card developer-release-card">
        <div className="deployment-card-title"><UploadCloud/><div><h2>Submit release document</h2><p>Developers select the application type, target country when applicable, owner and document. DevOps extracts and orchestrates after approval.</p></div></div>
        <div className="deployment-form">
          <label>Application type<select value={appType} onChange={e=>setAppType(e.target.value)}>{APP_TYPES.map(x=><option key={x}>{x}</option>)}</select></label>
          {appType==="Collections"&&<label>Collections country<select value={country} onChange={e=>setCountry(e.target.value)}>{COLLECTIONS_COUNTRIES.map(x=><option key={x}>{x}</option>)}</select></label>}
          <label>Application owner<input value={appOwner} onChange={e=>setAppOwner(e.target.value)} placeholder="owner@mashreq.com"/></label>
        </div>
        <label className="deployment-upload"><FileText/><input type="file" accept=".pdf,.docx,.txt,.md" onChange={e=>setFile(e.target.files?.[0]||null)}/><span>{file?.name||"Choose structured release document"}</span></label>
        <button className="primary-button" disabled={!file||!appOwner||busy} onClick={submitDocument}>{busy?"Submitting...":"Send for approval"}</button>
      </section>:
      <section className="deployment-grid devops-deployment-grid">
        <article className="deployment-card deployment-queue">
          <div className="deployment-card-title"><GitPullRequest/><div><h2>Deployment queue</h2><p>Select a request to extract and orchestrate.</p></div></div>
          {requests.length===0?<div className="monitoring-empty">No deployment requests.</div>:requests.slice(0,20).map(r=><button className={`deployment-request deployment-request-button ${selected?.id===r.id?"selected":""}`} key={r.id} onClick={()=>setSelected(r)}><div><span>{r.id}</span><h3>{r.application||r.application_type}</h3><p>{r.document_name} · {r.requested_by}{r.country?` · ${r.country}`:""}</p></div><span className="status warning">{r.status}</span></button>)}
        </article>

        <article className="deployment-card deployment-orchestrator">
          {!selected?<div className="monitoring-empty">Select a deployment request.</div>:<>
            <div className="deployment-card-title"><FileText/><div><h2>{selected.application_type}{selected.country?` · ${selected.country}`:""}</h2><p>{selected.id} · {selected.document_name}</p></div></div>
            <div className="deployment-step-row">{Object.entries(selected.steps||{}).map(([k,v])=><small key={k}><CheckCircle2 size={13}/>{k.split("_").join(" ")}: {v.status}</small>)}</div>
            {selected.status==="Pending App Owner Approval"&&<div className="deployment-actions"><button className="secondary-button" onClick={()=>action(selected.id,"owner-approve")}>Record owner approval</button><button className="danger-button" onClick={()=>action(selected.id,"owner-reject")}>Reject</button></div>}
            {selected.status!=="App Owner Rejected"&&<>
              <div className="deployment-actions"><button className="primary-button" disabled={busy} onClick={()=>action(selected.id,"extract-document")}>Extract structured data</button></div>
              {selected.extracted&&<>
                {selected.application_type==="Collections"?
                  <div className="collections-image-review">
                    <div className="deployment-result-header"><div><span className="eyebrow">COLLECTIONS IMAGE REVIEW</span><h3>{selected.country} build pipelines</h3></div><strong>{(selected.collections_items||[]).filter(x=>x.selected).length} selected</strong></div>
                    {(selected.collections_items||[]).length===0?<div className="monitoring-empty">No mapped Collections images were found in the document.</div>:<div className="table-card collections-image-table"><table><thead><tr><th>Select</th><th>Service</th><th>Image tag</th><th>Pipeline</th></tr></thead><tbody>{(selected.collections_items||[]).map((item,index)=><tr key={`${item.service}-${item.image_tag}`}><td><input type="checkbox" checked={item.selected} onChange={e=>updateCollectionItem(index,"selected",e.target.checked)}/></td><td><strong>{item.service}</strong></td><td>{item.image_tag}</td><td>{item.pipeline_name||<span className="status warning">Mapping missing</span>}</td></tr>)}</tbody></table></div>}
                  </div>:
                  <div className="deployment-form">
                    <label>Application<input value={selected.application||""} onChange={e=>updateSelected("application",e.target.value)}/></label>
                    <label>Source branch<input value={selected.branch_name||""} onChange={e=>updateSelected("branch_name",e.target.value)}/></label>
                    <label>Environment<input value={selected.environment||""} onChange={e=>updateSelected("environment",e.target.value)}/></label>
                    <label>Repository<input value={selected.repository||""} onChange={e=>updateSelected("repository",e.target.value)}/></label>
                    <label>PR target branch<input value={selected.target_branch||""} onChange={e=>updateSelected("target_branch",e.target.value)}/></label>
                    <label>Build pipeline<input value={selected.build_pipeline||""} onChange={e=>updateSelected("build_pipeline",e.target.value)}/></label>
                    <label>WAR files<input value={(selected.war_files||[]).join(", ")} onChange={e=>updateSelected("war_files",e.target.value.split(",").map(v=>v.trim()).filter(Boolean))}/></label>
                    <label>JAR files<input value={(selected.jar_files||[]).join(", ")} onChange={e=>updateSelected("jar_files",e.target.value.split(",").map(v=>v.trim()).filter(Boolean))}/></label>
                  </div>}
                <button className="secondary-button" onClick={saveUpdates}>Save extracted data</button>
                <label className="deployment-pat">Azure DevOps PAT<input type="password" value={pat} onChange={e=>setPat(e.target.value)} placeholder="Required for pipeline and PR actions"/></label>
                <div className="deployment-actions orchestration-actions">
                  {selected.application_type==="GTB-Applications"&&<><button className="primary-button" onClick={()=>action(selected.id,"trigger-code-pull")}><Play size={15}/>Code pull</button><button className="secondary-button" onClick={()=>action(selected.id,"create-pr")}>Raise PR</button></>}
                  <button className="primary-button" onClick={()=>action(selected.id,"trigger-build",selected.application_type==="Collections"?{collections_items:selected.collections_items||[]}:{})}>Trigger build</button>
                  <button className="primary-button" onClick={()=>{const name=window.prompt(`Deployment pipeline name${selected.country?` for ${selected.country}`:""} (leave blank to use configured value)`);void action(selected.id,"trigger-deployment",name?{pipeline_name:name}:{})}}>Trigger deployment</button>
                </div>
              </>}
            </>}
          </>}
        </article>
      </section>}
    {message&&<div className="deployment-message">{message}</div>}
  </div>;
}
