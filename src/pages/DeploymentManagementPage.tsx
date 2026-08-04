import { useEffect, useState } from "react";
import { CheckCircle2, FileText, GitPullRequest, Play, Rocket, UploadCloud } from "lucide-react";

const API_BASE = "/devops-portal/api";

type Extracted = {
  filename?: string;
  application: string;
  branch_name: string;
  environment: string;
  war_files: string[];
  jar_files: string[];
};

type DeploymentRequest = Extracted & {
  id: string;
  app_owner: string;
  repository: string;
  target_branch: string;
  status: string;
  requested_by: string;
  created_at: string;
  steps: Record<string, { status: string }>;
};

export default function DeploymentManagementPage({ token, role }: { token: string; role: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [data, setData] = useState<Extracted>({ application: "", branch_name: "", environment: "", war_files: [], jar_files: [] });
  const [appOwner, setAppOwner] = useState("");
  const [repository, setRepository] = useState("");
  const [targetBranch, setTargetBranch] = useState("release/uat");
  const [requests, setRequests] = useState<DeploymentRequest[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function loadRequests() {
    const response = await fetch(`${API_BASE}/deployment-management/requests`, { headers: { Authorization: `Bearer ${token}` } });
    if (response.ok) setRequests(await response.json());
  }

  useEffect(() => { void loadRequests(); }, [token]);

  async function extract() {
    if (!file) return;
    setBusy(true); setMessage("");
    const form = new FormData(); form.append("document", file);
    const response = await fetch(`${API_BASE}/deployment-management/extract`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
    const body = await response.json();
    setBusy(false);
    if (!response.ok) return setMessage(body.detail || "Unable to extract document");
    setData(body); setRepository(body.application || "");
  }

  async function submit() {
    setBusy(true); setMessage("");
    const response = await fetch(`${API_BASE}/deployment-management/requests`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ ...data, app_owner: appOwner, repository, target_branch: targetBranch, document_name: file?.name || data.filename || "" }),
    });
    const body = await response.json(); setBusy(false);
    if (!response.ok) return setMessage(body.detail || "Unable to submit deployment request");
    setMessage(`Deployment request ${body.id} submitted for application-owner approval.`);
    await loadRequests();
  }

  async function action(id: string, name: string) {
    const pat = name === "trigger-code-pull" ? window.prompt("Azure DevOps PAT") || "" : "";
    const response = await fetch(`${API_BASE}/deployment-management/requests/${id}/${name}`, {
      method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ azure_devops_pat: pat || null }),
    });
    const body = await response.json();
    setMessage(response.ok ? `${id} updated successfully.` : body.detail || "Action failed");
    if (response.ok) await loadRequests();
  }

  return <div className="deployment-management-page">
    <section className="deployment-hero">
      <div><span className="eyebrow">RELEASE ORCHESTRATION</span><h1>Deployment Management Dashboard</h1><p>Upload release documents, capture approval, orchestrate code pull, review pull requests, and trigger parameterized builds from one controlled workflow.</p></div>
      <Rocket size={44}/>
    </section>

    <div className="deployment-workflow">
      {["Release document", "App-owner approval", "DevOps review", "Code pull", "Pull request", "Build & deploy"].map((label, index) => <div key={label}><span>{index + 1}</span><strong>{label}</strong></div>)}
    </div>

    <section className="deployment-grid">
      <article className="deployment-card">
        <div className="deployment-card-title"><UploadCloud/><div><h2>New deployment request</h2><p>PDF and DOCX fields remain editable before submission.</p></div></div>
        <label className="deployment-upload"><FileText/><input type="file" accept=".pdf,.docx,.txt,.md" onChange={(event) => setFile(event.target.files?.[0] || null)}/><span>{file?.name || "Choose release document"}</span></label>
        <button className="primary-button" disabled={!file || busy} onClick={extract}>{busy ? "Processing..." : "Extract release details"}</button>
        <div className="deployment-form">
          <label>Application<input value={data.application} onChange={(e) => setData({...data, application:e.target.value})}/></label>
          <label>Source branch<input value={data.branch_name} onChange={(e) => setData({...data, branch_name:e.target.value})}/></label>
          <label>Environment<input value={data.environment} onChange={(e) => setData({...data, environment:e.target.value})}/></label>
          <label>Application owner<input value={appOwner} onChange={(e) => setAppOwner(e.target.value)} placeholder="owner@mashreq.com"/></label>
          <label>Repository<input value={repository} onChange={(e) => setRepository(e.target.value)}/></label>
          <label>PR target branch<input value={targetBranch} onChange={(e) => setTargetBranch(e.target.value)}/></label>
          <label>WAR files<input value={data.war_files.join(", ")} onChange={(e) => setData({...data, war_files:e.target.value.split(",").map(v=>v.trim()).filter(Boolean)})}/></label>
          <label>JAR files<input value={data.jar_files.join(", ")} onChange={(e) => setData({...data, jar_files:e.target.value.split(",").map(v=>v.trim()).filter(Boolean)})}/></label>
        </div>
        <button className="primary-button" disabled={busy} onClick={submit}>Submit for application-owner approval</button>
        {message && <div className="deployment-message">{message}</div>}
      </article>

      <article className="deployment-card deployment-queue">
        <div className="deployment-card-title"><GitPullRequest/><div><h2>Deployment queue</h2><p>Live workflow status for release requests.</p></div></div>
        {requests.length === 0 ? <div className="monitoring-empty">No deployment requests yet.</div> : requests.slice(0,10).map((request) => <div className="deployment-request" key={request.id}>
          <div><span>{request.id}</span><h3>{request.application}</h3><p>{request.branch_name} → {request.environment}</p></div>
          <span className="status warning">{request.status}</span>
          <div className="deployment-step-row">{Object.entries(request.steps || {}).map(([key,value]) => <small key={key} title={key}><CheckCircle2 size={13}/>{value.status}</small>)}</div>
          {role === "devops" && <div className="deployment-actions">
            {request.status === "Pending App Owner Approval" && <button className="secondary-button" onClick={() => action(request.id,"owner-approve")}>Record owner approval</button>}
            {request.status === "Awaiting DevOps" && <button className="primary-button" onClick={() => action(request.id,"trigger-code-pull")}><Play size={15}/>Trigger code pull</button>}
          </div>}
        </div>)}
      </article>
    </section>
  </div>;
}
