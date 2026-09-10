import { useEffect, useMemo, useState } from "react";
import { Boxes, FileText, GitPullRequest, Play, RefreshCw, Rocket, ShieldCheck, UploadCloud } from "lucide-react";

const API_BASE = "/devops-portal/api";
const APP_TYPES = ["H2H", "Collections", "GTB-Applications", "Native-Mobile", "Safenet"] as const;
const COLLECTIONS_COUNTRIES = ["UAE", "Egypt"];

type Run = {
  pipeline_name?: string;
  pipeline_id?: number;
  run_id?: number;
  release_id?: number;
  release_name?: string;
  release_definition_id?: number;
  release_definition_name?: string;
  status?: string;
  url?: string;
  logs_url?: string;
  duration_seconds?: number | null;
  service?: string;
  vendor_image?: string;
  use_vendor_image?: boolean;
  environment_status?: string;
  environments?: { id?: number; name?: string; status?: string; rank?: number }[];
};
type Step = { status: string; runs?: Run[]; discovery_missing?: Record<string, unknown>[] };
type CollectionsItem = {
  selected: boolean;
  service: string;
  image_tag: string;
  vendor_image: string;
  use_vendor_image?: boolean;
  extraction_method?: string;
  pipeline_name: string;
  country: string;
};
type DeploymentRequest = {
  id: string;
  application_type: string;
  application: string;
  branch_name: string;
  environment: string;
  country?: string;
  app_owner: string;
  repository: string;
  target_branch: string;
  build_pipeline: string;
  status: string;
  requested_by: string;
  created_at: string;
  document_name: string;
  extracted: boolean;
  progress_percent?: number;
  war_files: string[];
  jar_files: string[];
  container_images: string[];
  collections_items?: CollectionsItem[];
  steps: Record<string, Step>;
};

function statusClass(status?: string) {
  const value = String(status || "").toLowerCase();
  if (value.includes("succeed") || value.includes("complete") || value.includes("approved")) return "success";
  if (value.includes("fail") || value.includes("reject")) return "danger";
  if (value.includes("running") || value.includes("queued") || value.includes("pending") || value.includes("waiting")) return "warning";
  return "neutral";
}

function formatDuration(value?: number | null) {
  if (value === undefined || value === null) return "—";
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${minutes ? `${minutes}m ` : ""}${seconds}s`;
}

async function readResponse(response: Response): Promise<any> {
  const text = await response.text();
  if (!text) return {};
  try { return JSON.parse(text); }
  catch { return { detail: text.startsWith("Internal Server Error") ? "Backend returned an internal server error. Check backend logs." : text }; }
}

function nextStep(request: DeploymentRequest) {
  if (request.status === "Pending App Owner Approval") return "Approval";
  if (!request.extracted) return "Extraction";
  if (request.application_type === "GTB-Applications" && request.steps?.code_pull?.status !== "Not Required" && ["Waiting", "Pending"].includes(request.steps?.code_pull?.status || "")) return "Code Pull";
  if (request.application_type === "GTB-Applications" && ["Waiting", "Pending"].includes(request.steps?.pull_request?.status || "")) return "Pull Request";
  if (["Waiting", "Failed"].includes(request.steps?.build?.status || "Waiting")) return "Build";
  if (["Queued", "Running"].includes(request.steps?.build?.status || "")) return "Build Status";
  if (["Waiting", "Failed"].includes(request.steps?.deployment?.status || "Waiting")) return "Deployment";
  return "Deployment Status";
}

export default function DeploymentManagementPage({ token, role }: { token: string; role: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [appType, setAppType] = useState<string>("Collections");
  const [country, setCountry] = useState("UAE");
  const [appOwner, setAppOwner] = useState("");
  const [requests, setRequests] = useState<DeploymentRequest[]>([]);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selected, setSelected] = useState<DeploymentRequest | null>(null);
  const [showNewRequest, setShowNewRequest] = useState(role !== "devops");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [pat, setPat] = useState("");

  async function loadRequests() {
    const response = await fetch(`${API_BASE}/deployment-management/requests`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) return;
    const rows = (await readResponse(response)) as DeploymentRequest[];
    setRequests(rows);
    setSelected((current) => current ? rows.find((row) => row.id === current.id) || current : null);
  }

  useEffect(() => { void loadRequests(); }, [token]);

  async function submitDocument() {
    if (!file || !appOwner) return;
    setBusy(true); setMessage("");
    const form = new FormData();
    form.append("application_type", appType);
    form.append("app_owner", appOwner);
    if (appType === "Collections") form.append("country", country);
    form.append("document", file);
    try {
      const response = await fetch(`${API_BASE}/deployment-management/submit-document`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
      const body = await readResponse(response);
      if (!response.ok) { setMessage(body.detail || "Submission failed"); return; }
      const mailText = body.owner_mail_sent === false ? " Approval email was not sent; check SMTP configuration." : " Approval email sent to the application owner.";
      setMessage(`Request ${body.id} submitted.${mailText}`);
      setFile(null); setAppOwner(""); setShowNewRequest(false); await loadRequests();
    } finally { setBusy(false); }
  }

  async function action(id: string, name: string, updates: Record<string, unknown> = {}, silent = false) {
    if (!silent) { setBusy(true); setMessage(""); }
    try {
      const response = await fetch(`${API_BASE}/deployment-management/requests/${id}/${name}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ azure_devops_pat: pat || null, updates }),
      });
      const body = await readResponse(response);
      if (!response.ok) { if (!silent) setMessage(body.detail || "Action failed"); return; }
      setSelected(body);
      setRequests((rows) => rows.map((row) => row.id === body.id ? body : row));
      if (!silent) {
        const releaseCount = body?.application_type === "Collections" && name === "trigger-deployment" ? body?.steps?.deployment?.runs?.length || 0 : 0;
        setMessage(releaseCount ? `${releaseCount} linked Azure DevOps release${releaseCount === 1 ? "" : "s"} discovered and loaded for ${id}.` : `${name} completed for ${id}.`);
      }
    } catch (error) {
      if (!silent) setMessage(error instanceof Error ? error.message : "Action failed");
    } finally { if (!silent) setBusy(false); }
  }

  const autoRefreshRequired = useMemo(() => {
    const states = [selected?.steps?.build?.status, selected?.steps?.deployment?.status];
    return states.some((state) => state === "Queued" || state === "Running");
  }, [selected?.steps?.build?.status, selected?.steps?.deployment?.status]);

  useEffect(() => {
    if (!selected || !autoRefreshRequired) return;
    const timer = window.setInterval(() => void action(selected.id, "refresh-status", {}, true), 5000);
    return () => window.clearInterval(timer);
  }, [selected?.id, autoRefreshRequired, pat, token]);

  function updateCollectionItem(index: number, key: keyof CollectionsItem, value: string | boolean) {
    if (!selected) return;
    const items = [...(selected.collections_items || [])];
    items[index] = { ...items[index], [key]: value };
    setSelected({ ...selected, collections_items: items });
  }

  const counts = useMemo(() => Object.fromEntries(APP_TYPES.map((type) => [type, requests.filter((request) => request.application_type === type).length])), [requests]);
  const pending = requests.filter((request) => request.status === "Pending App Owner Approval");
  const visibleRequests = requests.filter((request) => !selectedType || request.application_type === selectedType);
  const buildRuns = selected?.steps?.build?.runs || [];
  const deploymentRuns = selected?.steps?.deployment?.runs || [];
  const buildLocked = buildRuns.length > 0;
  const selectedItems = (selected?.collections_items || []).filter((item) => item.selected);
  const collectionsBuildReady = selectedItems.length > 0 && selectedItems.every((item) => item.pipeline_name.trim() && ((item.use_vendor_image ?? true) ? item.vendor_image.trim() : true));

  async function startRequest(request: DeploymentRequest) {
    setSelected(request);
    setSelectedType(request.application_type);
    if (request.status === "Pending App Owner Approval") {
      const bypass = window.confirm("Owner approval is still pending. Click OK to bypass owner approval and continue as DevOps, or Cancel to keep it pending.");
      if (bypass) await action(request.id, "owner-approve", { bypass_owner_approval: true });
    }
  }

  function renderWizard() {
    if (!selected) return null;
    const step = nextStep(selected);
    return <section className="deployment-card deployment-wizard">
      <div className="deployment-wizard-header">
        <div><span className="eyebrow">{selected.application_type}</span><h2>{selected.application || selected.document_name}</h2><p>{selected.id} · {selected.country || selected.environment || "Environment pending"}</p></div>
        <div className="wizard-next-step"><span>Next step</span><strong>{step}</strong></div>
      </div>
      <div className="deployment-progress-card"><div><span>Overall progress</span><strong>{selected.progress_percent || 0}%</strong></div><div className="deployment-progress-track"><span style={{ width: `${selected.progress_percent || 0}%` }}/></div></div>

      {step === "Approval" && <div className="wizard-action-panel"><ShieldCheck/><div><h3>Application-owner approval pending</h3><p>Owner: {selected.app_owner}</p><div className="deployment-actions"><button className="primary-button" onClick={() => action(selected.id, "owner-approve")}>Record approval</button><button className="secondary-button" onClick={() => action(selected.id, "owner-approve", { bypass_owner_approval: true })}>Bypass approval</button><button className="danger-button" onClick={() => action(selected.id, "owner-reject")}>Reject</button></div></div></div>}

      {step === "Extraction" && <div className="wizard-action-panel"><FileText/><div><h3>Extract the release document</h3><p>The original uploaded document will be parsed and all deployment data will be populated.</p><button className="primary-button" disabled={busy} onClick={() => action(selected.id, "extract-document")}>Extract all document data</button></div></div>}

      {selected.extracted && selected.application_type === "Collections" && ["Build", "Build Status"].includes(step) && <div className="collections-build-panel">
        <div className="deployment-result-header"><div><span className="eyebrow">COLLECTIONS BUILD INPUT REVIEW</span><h3>{selected.country} vendor images</h3></div><strong>{selectedItems.length} selected</strong></div>
        <div className="table-card collections-image-table"><table><thead><tr><th>Select</th><th>Service</th><th>Tag</th><th>useVendorImage</th><th>vendorImage</th><th>Pipeline</th></tr></thead><tbody>
          {(selected.collections_items || []).map((item, index) => <tr key={`${item.service}-${index}`}>
            <td><input type="checkbox" checked={item.selected} disabled={buildLocked} onChange={(event) => updateCollectionItem(index, "selected", event.target.checked)}/></td>
            <td>{item.service}</td><td>{item.image_tag}</td>
            <td><button type="button" className={`vendor-toggle-button ${(item.use_vendor_image ?? true) ? "enabled" : "disabled"}`} disabled={!item.selected || buildLocked} onClick={() => updateCollectionItem(index, "use_vendor_image", !(item.use_vendor_image ?? true))}>{(item.use_vendor_image ?? true) ? "TRUE" : "FALSE"}</button></td>
            <td><input className="collections-vendor-image-input" value={item.vendor_image} disabled={!item.selected || !(item.use_vendor_image ?? true) || buildLocked} onChange={(event) => updateCollectionItem(index, "vendor_image", event.target.value)}/></td>
            <td>{item.pipeline_name || "Mapping missing"}</td>
          </tr>)}
        </tbody></table></div>
        {!buildLocked && <div className="deployment-actions"><button className="secondary-button" onClick={() => action(selected.id, "save-extracted-data", { collections_items: selected.collections_items || [] })}>Save reviewed data</button><button className="primary-button" disabled={!collectionsBuildReady || busy} onClick={() => action(selected.id, "trigger-build", { collections_items: selected.collections_items || [] })}>Trigger build</button></div>}
      </div>}

      {step === "Code Pull" && <div className="wizard-action-panel"><Play/><div><h3>Trigger code pull</h3><button className="primary-button" onClick={() => action(selected.id, "trigger-code-pull")}>Trigger code-pull pipeline</button></div></div>}
      {step === "Pull Request" && <div className="wizard-action-panel"><GitPullRequest/><div><h3>Raise pull request</h3><button className="primary-button" onClick={() => action(selected.id, "create-pr")}>Raise PR</button></div></div>}
      {step === "Build" && selected.application_type !== "Collections" && <div className="wizard-action-panel"><Boxes/><div><h3>Trigger build pipeline</h3><button className="primary-button" onClick={() => action(selected.id, "trigger-build")}>Trigger build</button></div></div>}

      {buildRuns.length > 0 && <div className="lifecycle-section"><div className="deployment-result-header"><h3>Build lifecycle</h3><span className={`status ${statusClass(selected.steps?.build?.status)}`}>{selected.steps?.build?.status}</span></div>{autoRefreshRequired && <p className="auto-refresh-note">Auto-refreshing every 5 seconds</p>}<div className="table-card lifecycle-table"><table><thead><tr><th>Service</th><th>Pipeline</th><th>Status</th><th>Duration</th><th>Link</th></tr></thead><tbody>{buildRuns.map((run, index) => <tr key={`${run.run_id}-${index}`}><td>{run.service || "—"}</td><td>{run.pipeline_name}</td><td><span className={`status ${statusClass(run.status)}`}>{run.status}</span></td><td>{formatDuration(run.duration_seconds)}</td><td>{run.url ? <a href={run.url} target="_blank" rel="noreferrer">Open</a> : "—"}</td></tr>)}</tbody></table></div></div>}

      {step === "Deployment" && <div className="wizard-action-panel"><Rocket/><div><h3>Trigger deployment</h3><p>Build status: {selected.steps?.build?.status}</p>{selected.application_type === "Collections" ? <><p>The portal will automatically discover the Classic Release linked to each successful build and load its environments and current status.</p><button className="primary-button" disabled={selected.steps?.build?.status !== "Succeeded" || busy} onClick={() => void action(selected.id, "trigger-deployment")}>{busy ? "Discovering release..." : "Trigger deployment"}</button></> : <button className="primary-button" onClick={() => { const name = window.prompt("Deployment pipeline name (leave blank to use configured value)"); void action(selected.id, "trigger-deployment", name ? { pipeline_name: name } : {}); }}>Trigger deployment</button>}</div></div>}

      {deploymentRuns.length > 0 && <div className="lifecycle-section"><div className="deployment-result-header"><h3>Deployment lifecycle</h3><span className={`status ${statusClass(selected.steps?.deployment?.status)}`}>{selected.steps?.deployment?.status}</span></div><div className="table-card lifecycle-table"><table><thead><tr><th>Service</th><th>Release</th><th>Release definition</th><th>Status</th><th>Duration</th><th>Environment</th><th>Link</th></tr></thead><tbody>{deploymentRuns.map((run, index) => <tr key={`${run.release_id || run.run_id}-${index}`}><td>{run.service || "—"}</td><td>{run.release_name || run.pipeline_name || "—"}{run.release_id ? <small>#{run.release_id}</small> : null}</td><td>{run.release_definition_name || run.pipeline_name || "—"}</td><td><span className={`status ${statusClass(run.status)}`}>{run.status}</span></td><td>{formatDuration(run.duration_seconds)}</td><td>{run.environment_status || selected.country || selected.environment}</td><td>{run.url ? <a href={run.url} target="_blank" rel="noreferrer">Open release</a> : "—"}</td></tr>)}</tbody></table></div></div>}

      <div className="deployment-actions"><button className="secondary-button" onClick={() => action(selected.id, "refresh-status")}><RefreshCw size={15}/>Refresh status</button><button className="secondary-button" onClick={() => setSelected(null)}>Back to dashboard</button></div>
      <label className="deployment-pat">Azure DevOps PAT<input type="password" value={pat} onChange={(event) => setPat(event.target.value)} placeholder="Optional when KUBERNETES_INVENTORY_PAT is configured"/></label>
    </section>;
  }

  return <div className="deployment-management-page">
    <section className="deployment-hero"><div><span className="eyebrow">RELEASE ORCHESTRATION</span><h1>Deployment Management Dashboard</h1><p>Application-specific deployment workflows, approvals, document extraction, builds and releases.</p></div><Rocket size={44}/></section>

    {!selected && <>
      <div className="application-management-grid">
        {APP_TYPES.map((type) => <button key={type} className={`application-management-card ${selectedType === type ? "active" : ""}`} onClick={() => setSelectedType(selectedType === type ? null : type)}><Boxes/><div><h3>{type} Deployment Management</h3><p>{counts[type] || 0} total requests</p></div><span>{requests.filter((request) => request.application_type === type && request.status === "Pending App Owner Approval").length} pending</span></button>)}
        <button className="application-management-card approval-card" onClick={() => setSelectedType("Pending Approvals")}><ShieldCheck/><div><h3>Pending Approvals</h3><p>All application types</p></div><span>{pending.length}</span></button>
      </div>

      {role === "devops" && <div className="dashboard-toolbar"><button className="primary-button" onClick={() => setShowNewRequest(!showNewRequest)}><UploadCloud size={16}/>New deployment request</button></div>}

      {showNewRequest && <section className="deployment-card developer-release-card"><div className="deployment-card-title"><UploadCloud/><div><h2>Raise deployment request</h2><p>Developers and DevOps can upload the structured release document.</p></div></div><div className="deployment-form"><label>Application type<select value={appType} onChange={(event) => setAppType(event.target.value)}>{APP_TYPES.map((type) => <option key={type}>{type}</option>)}</select></label>{appType === "Collections" && <label>Country<select value={country} onChange={(event) => setCountry(event.target.value)}>{COLLECTIONS_COUNTRIES.map((value) => <option key={value}>{value}</option>)}</select></label>}<label>Application owner<input value={appOwner} onChange={(event) => setAppOwner(event.target.value)} placeholder="owner@mashreq.com"/></label></div><label className="deployment-upload"><FileText/><input type="file" accept=".pdf,.docx,.txt,.md" onChange={(event) => setFile(event.target.files?.[0] || null)}/><span>{file?.name || "Choose structured release document"}</span></label><button className="primary-button" disabled={!file || !appOwner || busy} onClick={submitDocument}>{busy ? "Submitting..." : "Send for approval"}</button></section>}

      <section className="deployment-card request-dashboard"><div className="deployment-card-title"><GitPullRequest/><div><h2>{selectedType === "Pending Approvals" ? "Pending approvals" : selectedType ? `${selectedType} requests` : "All deployment requests"}</h2><p>Click a request to continue automatically from its next required step.</p></div></div>{(selectedType === "Pending Approvals" ? pending : visibleRequests).length === 0 ? <div className="monitoring-empty">No requests found.</div> : <div className="request-card-grid">{(selectedType === "Pending Approvals" ? pending : visibleRequests).map((request) => <button className="request-summary-card" key={request.id} onClick={() => void startRequest(request)}><div><span>{request.id}</span><h3>{request.application || request.application_type}</h3><p>{request.document_name}</p><p>{request.country || request.environment || "Environment pending"} · {request.requested_by}</p></div><div><span className={`status ${statusClass(request.status)}`}>{request.status}</span><small>Next: {nextStep(request)}</small></div></button>)}</div>}</section>
    </>}

    {renderWizard()}
    {message && <div className="deployment-message">{message}</div>}
  </div>;
}
