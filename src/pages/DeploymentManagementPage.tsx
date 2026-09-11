import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Boxes, ExternalLink, FileText, GitPullRequest, Play, RefreshCw, Rocket, Search, ShieldCheck, UploadCloud } from "lucide-react";
import PremiumDeploymentModal from "../components/PremiumDeploymentModal";

const API_BASE = "/devops-portal/api";
const PAT_SESSION_KEY = "devops-portal-azure-pat";
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

type Step = {
  status: string;
  actor?: string;
  at?: string;
  bypassed?: boolean;
  runs?: Run[];
  discovery_missing?: Record<string, unknown>[];
};

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

type InlineNotice = { variant: "success" | "warning" | "error" | "info"; message: string };
type Dialog =
  | { kind: "bypass"; request: DeploymentRequest }
  | { kind: "reject"; request: DeploymentRequest }
  | { kind: "pipeline"; request: DeploymentRequest; pipelineName: string };

function readSessionPat() {
  try { return sessionStorage.getItem(PAT_SESSION_KEY) || ""; }
  catch { return ""; }
}

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

function formatDate(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function approvalState(request: DeploymentRequest) {
  const step = request.steps?.owner_approval || { status: "Pending" };
  const value = String(step.status || "Pending").toLowerCase();
  if (value === "approved") {
    return {
      label: step.bypassed ? "Approval bypassed" : "Owner approved",
      className: step.bypassed ? "warning" : "success",
      detail: step.actor ? `by ${step.actor}` : "Approved",
    };
  }
  if (value === "rejected") return { label: "Owner rejected", className: "danger", detail: step.actor ? `by ${step.actor}` : "Rejected" };
  return { label: "Owner approval pending", className: "warning", detail: request.app_owner || "Awaiting owner" };
}

async function readResponse(response: Response): Promise<any> {
  const text = await response.text();
  if (!text) return {};
  try { return JSON.parse(text); }
  catch { return { detail: text.startsWith("Internal Server Error") ? "Backend returned an internal server error. Check backend logs." : text }; }
}

function nextStep(request: DeploymentRequest) {
  const approval = String(request.steps?.owner_approval?.status || "Pending");
  if (approval === "Rejected") return "Rejected";
  if (approval !== "Approved") return "Approval";
  if (!request.extracted) return "Extraction";
  if (request.application_type === "GTB-Applications" && request.steps?.code_pull?.status !== "Not Required" && ["Waiting", "Pending"].includes(request.steps?.code_pull?.status || "")) return "Code Pull";
  if (request.application_type === "GTB-Applications" && ["Waiting", "Pending"].includes(request.steps?.pull_request?.status || "")) return "Pull Request";
  if (["Waiting", "Failed"].includes(request.steps?.build?.status || "Waiting")) return "Build";
  if (["Queued", "Running"].includes(request.steps?.build?.status || "")) return "Build Status";
  if (["Waiting", "Failed"].includes(request.steps?.deployment?.status || "Waiting")) return "Deployment";
  return "Deployment Status";
}

export default function DeploymentManagementPage({ token, role, isAdmin }: { token: string; role: string; isAdmin: boolean }) {
  const [file, setFile] = useState<File | null>(null);
  const [appType, setAppType] = useState<string>("Collections");
  const [country, setCountry] = useState("UAE");
  const [appOwner, setAppOwner] = useState("");
  const [requests, setRequests] = useState<DeploymentRequest[]>([]);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selected, setSelected] = useState<DeploymentRequest | null>(null);
  const [showNewRequest, setShowNewRequest] = useState(role !== "devops");
  const [busy, setBusy] = useState(false);
  const [inlineNotice, setInlineNotice] = useState<InlineNotice | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [requestSearch, setRequestSearch] = useState("");
  const [pat, setPat] = useState(readSessionPat);
  const [patEditable, setPatEditable] = useState(false);
  const collectionsDirtyRef = useRef(false);

  async function loadRequests() {
    const response = await fetch(`${API_BASE}/deployment-management/requests`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) return;
    const rows = (await readResponse(response)) as DeploymentRequest[];
    setRequests(rows);
    setSelected((current) => {
      if (!current) return null;
      const fresh = rows.find((row) => row.id === current.id);
      if (!fresh) return current;
      if (collectionsDirtyRef.current && current.application_type === "Collections") {
        return { ...fresh, collections_items: current.collections_items };
      }
      return fresh;
    });
  }

  useEffect(() => { void loadRequests(); }, [token]);
  useEffect(() => {
    const timer = window.setInterval(() => void loadRequests(), 10000);
    return () => window.clearInterval(timer);
  }, [token]);
  useEffect(() => {
    try {
      if (pat) sessionStorage.setItem(PAT_SESSION_KEY, pat);
      else sessionStorage.removeItem(PAT_SESSION_KEY);
    } catch { /* session storage unavailable */ }
  }, [pat]);

  async function submitDocument() {
    if (!file || !appOwner) return;
    setBusy(true); setInlineNotice(null);
    const form = new FormData();
    form.append("application_type", appType);
    form.append("app_owner", appOwner);
    if (appType === "Collections") form.append("country", country);
    form.append("document", file);
    try {
      const response = await fetch(`${API_BASE}/deployment-management/submit-document`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
      const body = await readResponse(response);
      if (!response.ok) {
        setInlineNotice({ variant: "error", message: body.detail || "Submission failed" });
        return;
      }
      setInlineNotice({
        variant: body.owner_mail_sent === false ? "warning" : "success",
        message: body.owner_mail_sent === false
          ? `Request ${body.id} was created, but the owner email was not sent. Check SMTP configuration.`
          : `Request ${body.id} was submitted and the approval email was sent to the application owner.`,
      });
      setFile(null); setAppOwner(""); setShowNewRequest(false); await loadRequests();
    } catch (error) {
      setInlineNotice({ variant: "error", message: error instanceof Error ? error.message : "Submission failed" });
    } finally { setBusy(false); }
  }

  async function action(id: string, name: string, updates: Record<string, unknown> = {}, silent = false) {
    if (!silent) { setBusy(true); setInlineNotice(null); }
    try {
      const response = await fetch(`${API_BASE}/deployment-management/requests/${id}/${name}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ azure_devops_pat: pat || null, updates }),
      });
      const body = await readResponse(response);
      if (!response.ok) {
        if (!silent) setInlineNotice({ variant: "error", message: body.detail || "The requested operation failed." });
        return;
      }
      if (["save-extracted-data", "trigger-build", "extract-document"].includes(name)) {
        collectionsDirtyRef.current = false;
      }
      setSelected(body);
      setRequests((rows) => rows.map((row) => row.id === body.id ? body : row));
      if (!silent) {
        const releaseCount = body?.application_type === "Collections" && name === "trigger-deployment" ? body?.steps?.deployment?.runs?.length || 0 : 0;
        const actionLabel = name.split("-").join(" ");
        setInlineNotice({
          variant: "success",
          message: releaseCount
            ? `${releaseCount} linked Azure DevOps release${releaseCount === 1 ? "" : "s"} discovered and loaded for ${id}.`
            : `${actionLabel} completed for ${id}.`,
        });
      }
    } catch (error) {
      if (!silent) setInlineNotice({ variant: "error", message: error instanceof Error ? error.message : "Action failed" });
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
    collectionsDirtyRef.current = true;
    const items = [...(selected.collections_items || [])];
    items[index] = { ...items[index], [key]: value };
    setSelected({ ...selected, collections_items: items });
  }

  const counts = useMemo(() => Object.fromEntries(APP_TYPES.map((type) => [type, requests.filter((request) => request.application_type === type).length])), [requests]);
  const pending = requests.filter((request) => String(request.steps?.owner_approval?.status || "Pending") === "Pending");
  const scopedRequests = selectedType === "Pending Approvals"
    ? pending
    : selectedType
      ? requests.filter((request) => request.application_type === selectedType)
      : requests;
  const displayedRequests = useMemo(() => {
    const query = requestSearch.trim().toLowerCase();
    if (!query) return scopedRequests;
    return scopedRequests.filter((request) => [
      request.id,
      request.application_type,
      request.application,
      request.country,
      request.environment,
      request.requested_by,
      request.app_owner,
      request.document_name,
      request.status,
      nextStep(request),
    ].some((value) => String(value || "").toLowerCase().includes(query)));
  }, [scopedRequests, requestSearch]);

  const buildRuns = selected?.steps?.build?.runs || [];
  const deploymentRuns = selected?.steps?.deployment?.runs || [];
  const buildLocked = buildRuns.length > 0;
  const selectedItems = (selected?.collections_items || []).filter((item) => item.selected && item.vendor_image.trim() && item.pipeline_name.trim());
  const collectionsBuildReady = selectedItems.length > 0 && selectedItems.every((item) => ((item.use_vendor_image ?? true) ? item.vendor_image.trim() : true));

  function startRequest(request: DeploymentRequest) {
    collectionsDirtyRef.current = false;
    setInlineNotice(null);
    setSelected(request);
  }

  async function confirmDialog() {
    if (!dialog) return;
    const current = dialog;
    setDialog(null);
    if (current.kind === "bypass") {
      if (!isAdmin) {
        setInlineNotice({ variant: "error", message: "Only a DevOps Admin can bypass application-owner approval." });
        return;
      }
      await action(current.request.id, "owner-approve", { bypass_owner_approval: true });
    } else if (current.kind === "reject") {
      await action(current.request.id, "owner-reject");
    } else if (current.kind === "pipeline") {
      const pipelineName = current.pipelineName.trim();
      await action(current.request.id, "trigger-deployment", pipelineName ? { pipeline_name: pipelineName } : {});
    }
  }

  function renderDialog() {
    if (!dialog) return null;
    if (dialog.kind === "bypass") {
      if (!isAdmin) return null;
      return <PremiumDeploymentModal open variant="warning" eyebrow="DEVOPS ADMIN APPROVAL" title="Bypass application-owner approval?" message="This privileged action is available only to DevOps Admins. Continue only when there is an authorized reason to bypass the owner approval gate." details={[{ label: "Request", value: dialog.request.id }, { label: "Application", value: dialog.request.application || dialog.request.application_type }, { label: "Owner", value: dialog.request.app_owner }]} primaryLabel="Yes, bypass approval" secondaryLabel="Keep pending" busy={busy} onPrimary={() => void confirmDialog()} onSecondary={() => setDialog(null)} />;
    }
    if (dialog.kind === "reject") return <PremiumDeploymentModal open variant="error" eyebrow="RELEASE DECISION" title="Reject this deployment request?" message="This stops the release workflow for this request and records the owner decision as rejected." details={[{ label: "Request", value: dialog.request.id }, { label: "Application", value: dialog.request.application || dialog.request.application_type }]} primaryLabel="Reject request" secondaryLabel="Cancel" busy={busy} onPrimary={() => void confirmDialog()} onSecondary={() => setDialog(null)} />;
    return <PremiumDeploymentModal open variant="info" eyebrow="DEPLOYMENT PIPELINE" title="Deployment pipeline" message="Enter the deployment pipeline name or leave it empty to use the pipeline configured for this application type." details={[{ label: "Request", value: dialog.request.id }, { label: "Application", value: dialog.request.application || dialog.request.application_type }]} inputLabel="Deployment pipeline name" inputValue={dialog.pipelineName} inputPlaceholder="Leave blank to use configured value" onInputChange={(value) => setDialog({ ...dialog, pipelineName: value })} primaryLabel="Trigger deployment" secondaryLabel="Cancel" busy={busy} onPrimary={() => void confirmDialog()} onSecondary={() => setDialog(null)} />;
  }

  function renderWizard() {
    if (!selected) return null;
    const step = nextStep(selected);
    const approval = approvalState(selected);
    return <section className="deployment-card deployment-wizard">
      <div className="deployment-wizard-header">
        <div><span className="eyebrow">{selected.application_type}</span><h2>{selected.application || selected.document_name}</h2><p>{selected.id} · {selected.country || selected.environment || "Environment pending"}</p></div>
        <div className="deployment-wizard-state"><span className={`owner-approval-badge ${approval.className}`}>{approval.label}</span><div className="wizard-next-step"><span>Next step</span><strong>{step}</strong></div></div>
      </div>
      {inlineNotice && <div className={`deployment-inline-notice ${inlineNotice.variant}`}>{inlineNotice.message}</div>}
      <div className="deployment-progress-card"><div><span>Overall progress</span><strong>{selected.progress_percent || 0}%</strong></div><div className="deployment-progress-track"><span style={{ width: `${selected.progress_percent || 0}%` }}/></div></div>

      {step === "Approval" && <div className="wizard-action-panel"><ShieldCheck/><div><h3>Application-owner approval pending</h3><p>Owner: {selected.app_owner}. The owner can approve or reject directly from the release email.</p>{role === "devops" ? <><div className="approval-wait-note">{isAdmin ? "As a DevOps Admin, you can manually record or bypass approval when authorized." : "Waiting for the application owner. Only a DevOps Admin can manually approve or bypass this gate."}</div><div className="deployment-actions">{isAdmin&&<><button className="primary-button" onClick={() => action(selected.id, "owner-approve")}>Record approval</button><button className="secondary-button" onClick={() => setDialog({ kind: "bypass", request: selected })}>Bypass approval</button></>}<button className="danger-button" onClick={() => setDialog({ kind: "reject", request: selected })}>Reject</button></div></> : <div className="approval-wait-note">Waiting for the application owner to respond from the approval email.</div>}</div></div>}

      {step === "Rejected" && <div className="wizard-action-panel"><ShieldCheck/><div><h3>Release request rejected</h3><p>The application owner rejected this request. Raise a new deployment request when the release is ready again.</p></div></div>}

      {step === "Extraction" && <div className="wizard-action-panel"><FileText/><div><h3>Extract the release document</h3><p>The document will be parsed and only actionable release inputs will be shown. For Collections, base nginx/JDK images and unmapped images are ignored.</p>{role === "devops" && <button className="primary-button" disabled={busy} onClick={() => action(selected.id, "extract-document")}>Extract release data</button>}</div></div>}

      {selected.extracted && selected.application_type === "Collections" && ["Build", "Build Status"].includes(step) && <div className="collections-build-panel">
        <div className="deployment-result-header"><div><span className="eyebrow">COLLECTIONS BUILD INPUT REVIEW</span><h3>{selected.country} vendor images</h3><p>Only services with vendor image tags and mapped build pipelines are included.</p></div><strong>{selectedItems.length} selected</strong></div>
        <div className="table-card collections-image-table"><table><thead><tr><th>Select</th><th>Service</th><th>Tag</th><th>useVendorImage</th><th>vendorImage</th><th>Pipeline</th></tr></thead><tbody>
          {(selected.collections_items || []).map((item, itemIndex) => ({ item, itemIndex })).filter(({ item }) => item.vendor_image.trim() && item.pipeline_name.trim()).map(({ item, itemIndex }) => <tr key={`${item.service}-${itemIndex}`}>
            <td><input type="checkbox" checked={item.selected} disabled={buildLocked || role !== "devops"} onChange={(event) => updateCollectionItem(itemIndex, "selected", event.target.checked)}/></td>
            <td>{item.service}</td><td>{item.image_tag}</td>
            <td><button type="button" className={`vendor-toggle-button ${(item.use_vendor_image ?? true) ? "enabled" : "disabled"}`} disabled={!item.selected || buildLocked || role !== "devops"} onClick={() => updateCollectionItem(itemIndex, "use_vendor_image", !(item.use_vendor_image ?? true))}>{(item.use_vendor_image ?? true) ? "TRUE" : "FALSE"}</button></td>
            <td><input className="collections-vendor-image-input" value={item.vendor_image} disabled={!item.selected || !(item.use_vendor_image ?? true) || buildLocked || role !== "devops"} onChange={(event) => updateCollectionItem(itemIndex, "vendor_image", event.target.value)}/></td>
            <td>{item.pipeline_name}</td>
          </tr>)}
        </tbody></table></div>
        {!buildLocked && role === "devops" && <div className="deployment-actions"><button className="secondary-button" onClick={() => action(selected.id, "save-extracted-data", { collections_items: selected.collections_items || [] })}>Save reviewed data</button><button className="primary-button" disabled={!collectionsBuildReady || busy} onClick={() => action(selected.id, "trigger-build", { collections_items: selected.collections_items || [] })}>Trigger build</button></div>}
      </div>}

      {step === "Code Pull" && role === "devops" && <div className="wizard-action-panel"><Play/><div><h3>Trigger code pull</h3><button className="primary-button" onClick={() => action(selected.id, "trigger-code-pull")}>Trigger code-pull pipeline</button></div></div>}
      {step === "Pull Request" && role === "devops" && <div className="wizard-action-panel"><GitPullRequest/><div><h3>Raise pull request</h3><button className="primary-button" onClick={() => action(selected.id, "create-pr")}>Raise PR</button></div></div>}
      {step === "Build" && selected.application_type !== "Collections" && role === "devops" && <div className="wizard-action-panel"><Boxes/><div><h3>Trigger build pipeline</h3><button className="primary-button" onClick={() => action(selected.id, "trigger-build")}>Trigger build</button></div></div>}

      {buildRuns.length > 0 && <div className="lifecycle-section"><div className="deployment-result-header"><h3>Build lifecycle</h3><span className={`status ${statusClass(selected.steps?.build?.status)}`}>{selected.steps?.build?.status}</span></div>{autoRefreshRequired && <p className="auto-refresh-note">Auto-refreshing every 5 seconds</p>}<div className="table-card lifecycle-table"><table><thead><tr><th>Service</th><th>Pipeline</th><th>Status</th><th>Duration</th><th>Link</th></tr></thead><tbody>{buildRuns.map((run, index) => <tr key={`${run.run_id}-${index}`}><td>{run.service || "—"}</td><td>{run.pipeline_name}</td><td><span className={`status ${statusClass(run.status)}`}>{run.status}</span></td><td>{formatDuration(run.duration_seconds)}</td><td>{run.url ? <a href={run.url} target="_blank" rel="noreferrer" title="Open build in Azure DevOps" aria-label="Open build in Azure DevOps"><ExternalLink size={17}/> Open</a> : "—"}</td></tr>)}</tbody></table></div></div>}

      {step === "Deployment" && role === "devops" && <div className="wizard-action-panel"><Rocket/><div><h3>Trigger deployment</h3><p>Build status: {selected.steps?.build?.status}</p>{selected.application_type === "Collections" ? <><p>The portal will discover the Classic Releases linked to the successful builds and load their environments and current status.</p><button className="primary-button" disabled={selected.steps?.build?.status !== "Succeeded" || busy} onClick={() => void action(selected.id, "trigger-deployment")}>{busy ? "Discovering release..." : "Trigger deployment"}</button></> : <button className="primary-button" onClick={() => setDialog({ kind: "pipeline", request: selected, pipelineName: "" })}>Trigger deployment</button>}</div></div>}

      {deploymentRuns.length > 0 && <div className="lifecycle-section"><div className="deployment-result-header"><h3>Deployment lifecycle</h3><span className={`status ${statusClass(selected.steps?.deployment?.status)}`}>{selected.steps?.deployment?.status}</span></div><div className="table-card lifecycle-table"><table><thead><tr><th>Service</th><th>Release</th><th>Release definition</th><th>Status</th><th>Duration</th><th>Environment</th><th>Link</th></tr></thead><tbody>{deploymentRuns.map((run, index) => <tr key={`${run.release_id || run.run_id}-${index}`}><td>{run.service || "—"}</td><td>{run.release_name || run.pipeline_name || "—"}{run.release_id ? <small>#{run.release_id}</small> : null}</td><td>{run.release_definition_name || run.pipeline_name || "—"}</td><td><span className={`status ${statusClass(run.status)}`}>{run.status}</span></td><td>{formatDuration(run.duration_seconds)}</td><td>{run.environment_status || selected.country || selected.environment}</td><td>{run.url ? <a href={run.url} target="_blank" rel="noreferrer" title="Open release in Azure DevOps" aria-label="Open release in Azure DevOps"><ExternalLink size={17}/> Open release</a> : "—"}</td></tr>)}</tbody></table></div></div>}

      <div className="deployment-actions">{role === "devops" && <button className="secondary-button" onClick={() => action(selected.id, "refresh-status")}><RefreshCw size={15}/>Refresh status</button>}<button className="secondary-button" onClick={() => { collectionsDirtyRef.current = false; setSelected(null); setInlineNotice(null); }}><ArrowLeft size={15}/>Back to requests</button></div>
      {role === "devops" && <div className="deployment-pat-card"><label className="deployment-pat">Azure DevOps PAT<input type="password" name="azure-devops-session-pat" value={pat} onChange={(event) => setPat(event.target.value)} onFocus={() => setPatEditable(true)} readOnly={!patEditable} autoComplete="new-password" data-lpignore="true" data-1p-ignore="true" spellCheck={false} placeholder="Enter once for this login session"/></label><div className="pat-session-note"><span>{pat ? "PAT available for this session" : "No session PAT entered"}</span><small>The token is kept only in this browser session and is cleared on logout.</small>{pat && <button type="button" className="secondary-button" onClick={() => { setPat(""); setPatEditable(true); }}>Clear PAT</button>}</div></div>}
    </section>;
  }

  const scopeTitle = selectedType === "Pending Approvals" ? "Pending approvals" : selectedType ? `${selectedType} deployment requests` : "All deployment requests";

  return <div className="deployment-management-page">
    <section className="deployment-hero"><div><span className="eyebrow">RELEASE ORCHESTRATION</span><h1>Deployment Management Dashboard</h1><p>Application-specific deployment workflows, approvals, document extraction, builds and releases.</p></div><Rocket size={44}/></section>

    {!selected && <>
      {!selectedType ? <div className="application-management-grid">
        {APP_TYPES.map((type) => <button key={type} className="application-management-card" onClick={() => { setSelectedType(type); setRequestSearch(""); setInlineNotice(null); }}><Boxes/><div><h3>{type} Deployment Management</h3><p>{counts[type] || 0} total requests</p></div><span>{requests.filter((request) => request.application_type === type && String(request.steps?.owner_approval?.status || "Pending") === "Pending").length} pending</span></button>)}
        <button className="application-management-card approval-card" onClick={() => { setSelectedType("Pending Approvals"); setRequestSearch(""); setInlineNotice(null); }}><ShieldCheck/><div><h3>Pending Approvals</h3><p>All application types</p></div><span>{pending.length}</span></button>
      </div> : <section className="deployment-scope-header"><button className="deployment-back-button" onClick={() => { setSelectedType(null); setRequestSearch(""); setInlineNotice(null); }}><ArrowLeft size={17}/>All applications</button><div><span className="eyebrow">FILTERED DEPLOYMENT VIEW</span><h2>{scopeTitle}</h2><p>Only requests for this selection are shown below.</p></div><strong>{scopedRequests.length}</strong></section>}

      {role === "devops" && <div className="dashboard-toolbar"><button className="primary-button" onClick={() => setShowNewRequest(!showNewRequest)}><UploadCloud size={16}/>{showNewRequest ? "Hide request form" : "New deployment request"}</button></div>}

      {showNewRequest && <section className="deployment-card developer-release-card"><div className="deployment-card-title"><UploadCloud/><div><h2>Raise deployment request</h2><p>Developers and DevOps can upload the structured release document.</p></div></div><div className="deployment-form"><label>Application type<select value={appType} onChange={(event) => setAppType(event.target.value)}>{APP_TYPES.map((type) => <option key={type}>{type}</option>)}</select></label>{appType === "Collections" && <label>Country<select value={country} onChange={(event) => setCountry(event.target.value)}>{COLLECTIONS_COUNTRIES.map((value) => <option key={value}>{value}</option>)}</select></label>}<label>Application owner<input value={appOwner} onChange={(event) => setAppOwner(event.target.value)} placeholder="owner@mashreq.com"/></label></div><label className="deployment-upload"><FileText/><input type="file" accept=".pdf,.docx,.txt,.md" onChange={(event) => setFile(event.target.files?.[0] || null)}/><span>{file?.name || "Choose structured release document"}</span></label><button className="primary-button" disabled={!file || !appOwner || busy} onClick={submitDocument}>{busy ? "Submitting..." : "Send for approval"}</button></section>}

      {inlineNotice && <div className={`deployment-inline-notice ${inlineNotice.variant}`}>{inlineNotice.message}</div>}

      <section className="deployment-card request-dashboard">
        <div className="deployment-request-toolbar"><div className="deployment-card-title"><GitPullRequest/><div><h2>{scopeTitle}</h2><p>Search by request ID, application, environment, owner, requester, document or status.</p></div></div><div className="deployment-request-search"><Search size={17}/><input value={requestSearch} onChange={(event) => setRequestSearch(event.target.value)} placeholder="Find deployment request..."/><span>{displayedRequests.length}</span></div></div>
        {displayedRequests.length === 0 ? <div className="monitoring-empty">No deployment requests match this view.</div> : <div className="deployment-request-list">
          <div className="deployment-request-list-head"><span>Request</span><span>Application</span><span>Environment</span><span>Requested by</span><span>Owner approval</span><span>Status</span><span>Next step</span></div>
          {displayedRequests.map((request) => { const approval = approvalState(request); return <button className="deployment-request-row" key={request.id} onClick={() => startRequest(request)}>
            <span className="request-id-cell"><strong>{request.id}</strong><small>{formatDate(request.created_at)}</small></span>
            <span><strong>{request.application || request.application_type}</strong><small>{request.document_name}</small></span>
            <span><strong>{request.country || request.environment || "Pending"}</strong><small>{request.application_type}</small></span>
            <span><strong>{request.requested_by}</strong><small>{request.app_owner}</small></span>
            <span className="owner-approval-cell"><span className={`owner-approval-badge ${approval.className}`}>{approval.label}</span><small>{approval.detail}</small></span>
            <span><span className={`status ${statusClass(request.status)}`}>{request.status}</span></span>
            <span className="request-next-step"><strong>{nextStep(request)}</strong><small>{request.progress_percent || 0}% complete</small></span>
          </button>; })}
        </div>}
      </section>
    </>}

    {renderWizard()}
    {renderDialog()}
  </div>;
}
