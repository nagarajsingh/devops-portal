import { useEffect, useMemo, useState } from "react";
import { FileText, GitPullRequest, Play, RefreshCw, Rocket, UploadCloud } from "lucide-react";

const API_BASE = "/devops-portal/api";
const APP_TYPES = ["H2H", "Collections", "GTB-Applications", "Native-Mobile", "Safenet"];
const COLLECTIONS_COUNTRIES = ["UAE", "Egypt"];
const STAGES = ["Document", "Owner approval", "DevOps extraction", "Code pull / PR", "Build", "Deployment"] as const;
type Stage = typeof STAGES[number];

type Run = {
  pipeline_name?: string;
  pipeline_id?: number;
  run_id?: number;
  release_id?: number;
  status?: string;
  result?: string;
  url?: string;
  logs_url?: string;
  duration_seconds?: number | null;
  service?: string;
  vendor_image?: string;
  use_vendor_image?: boolean;
  environment_status?: string;
};
type Step = { status: string; runs?: Run[] };
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
  if (value.includes("running") || value.includes("queued") || value.includes("pending")) return "warning";
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
  try {
    return JSON.parse(text);
  } catch {
    return {
      detail: text.startsWith("Internal Server Error")
        ? "Backend returned an internal server error. Check the backend logs."
        : text,
    };
  }
}

export default function DeploymentManagementPage({ token, role }: { token: string; role: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [appType, setAppType] = useState("GTB-Applications");
  const [country, setCountry] = useState("UAE");
  const [appOwner, setAppOwner] = useState("");
  const [requests, setRequests] = useState<DeploymentRequest[]>([]);
  const [selected, setSelected] = useState<DeploymentRequest | null>(null);
  const [activeStage, setActiveStage] = useState<Stage>("Document");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [pat, setPat] = useState("");

  async function loadRequests() {
    const response = await fetch(`${API_BASE}/deployment-management/requests`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) return;
    const rows = (await readResponse(response)) as DeploymentRequest[];
    setRequests(rows);
    setSelected((current) => current ? rows.find((row) => row.id === current.id) || current : null);
  }

  useEffect(() => {
    void loadRequests();
  }, [token]);

  async function submitDocument() {
    if (!file || !appOwner) return;
    setBusy(true);
    setMessage("");
    const form = new FormData();
    form.append("application_type", appType);
    form.append("app_owner", appOwner);
    if (appType === "Collections") form.append("country", country);
    form.append("document", file);
    try {
      const response = await fetch(`${API_BASE}/deployment-management/submit-document`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const body = await readResponse(response);
      setMessage(response.ok ? `Request ${body.id} submitted for approval.` : body.detail || "Submission failed");
      if (response.ok) {
        setFile(null);
        await loadRequests();
      }
    } finally {
      setBusy(false);
    }
  }

  async function action(
    id: string,
    name: string,
    updates: Record<string, unknown> = {},
    silent = false,
  ) {
    if (!silent) {
      setBusy(true);
      setMessage("");
    }
    try {
      const response = await fetch(`${API_BASE}/deployment-management/requests/${id}/${name}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ azure_devops_pat: pat || null, updates }),
      });
      const body = await readResponse(response);
      if (!response.ok) {
        if (!silent) setMessage(body.detail || "Action failed");
        return;
      }
      setSelected(body);
      setRequests((rows) => rows.map((row) => row.id === body.id ? body : row));
      if (!silent) setMessage(`${name} completed for ${id}.`);
    } catch (error) {
      if (!silent) setMessage(error instanceof Error ? error.message : "Action failed");
    } finally {
      if (!silent) setBusy(false);
    }
  }

  const autoRefreshRequired = useMemo(() => {
    const states = [selected?.steps?.build?.status, selected?.steps?.deployment?.status];
    return states.some((state) => state === "Queued" || state === "Running");
  }, [selected?.steps?.build?.status, selected?.steps?.deployment?.status]);

  useEffect(() => {
    if (!selected || !autoRefreshRequired) return;
    const timer = window.setInterval(() => {
      void action(selected.id, "refresh-status", {}, true);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [selected?.id, autoRefreshRequired, pat, token]);

  function updateSelected(key: keyof DeploymentRequest, value: unknown) {
    if (selected) setSelected({ ...selected, [key]: value } as DeploymentRequest);
  }

  function updateCollectionItem(index: number, key: keyof CollectionsItem, value: string | boolean) {
    if (!selected) return;
    const items = [...(selected.collections_items || [])];
    items[index] = { ...items[index], [key]: value };
    setSelected({ ...selected, collections_items: items });
  }

  const saveUpdates = () => selected && action(selected.id, "save-extracted-data", {
    application: selected.application,
    branch_name: selected.branch_name,
    environment: selected.environment,
    repository: selected.repository,
    target_branch: selected.target_branch,
    build_pipeline: selected.build_pipeline,
    war_files: selected.war_files,
    jar_files: selected.jar_files,
    container_images: selected.container_images,
    collections_items: selected.collections_items || [],
  });

  const buildRuns = selected?.steps?.build?.runs || [];
  const deploymentRuns = selected?.steps?.deployment?.runs || [];
  const buildLocked = buildRuns.length > 0;
  const selectedItems = (selected?.collections_items || []).filter((item) => item.selected);
  const collectionsBuildReady = selectedItems.length > 0 && selectedItems.every((item) =>
    item.pipeline_name.trim() && ((item.use_vendor_image ?? true) ? item.vendor_image.trim() : true),
  );

  function renderStage() {
    if (!selected) return <div className="monitoring-empty">Select a request from the queue.</div>;

    if (activeStage === "Document") {
      return <div className="deployment-stage-dashboard">
        <h2>Document</h2>
        <p><strong>{selected.document_name}</strong></p>
        <p>{selected.application_type}{selected.country ? ` · ${selected.country}` : ""}</p>
        <p>Requested by: {selected.requested_by}</p>
        <span className={`status ${statusClass(selected.status)}`}>{selected.status}</span>
      </div>;
    }

    if (activeStage === "Owner approval") {
      return <div className="deployment-stage-dashboard">
        <h2>Owner approval</h2>
        <p>Application owner: {selected.app_owner}</p>
        {selected.status === "Pending App Owner Approval"
          ? <div className="deployment-actions">
              <button className="primary-button" onClick={() => action(selected.id, "owner-approve")}>Record approval</button>
              <button className="danger-button" onClick={() => action(selected.id, "owner-reject")}>Reject</button>
            </div>
          : <span className={`status ${statusClass(selected.steps?.owner_approval?.status)}`}>{selected.steps?.owner_approval?.status || selected.status}</span>}
      </div>;
    }

    if (activeStage === "DevOps extraction") {
      return <div className="deployment-stage-dashboard">
        <h2>DevOps extraction</h2>
        <p>Re-extract reads the original uploaded document again and replaces all extracted fields.</p>
        <button className="primary-button" disabled={busy} onClick={() => action(selected.id, "extract-document")}>
          {selected.extracted ? "Re-extract all data" : "Extract document"}
        </button>
      </div>;
    }

    if (activeStage === "Code pull / PR") {
      return <div className="deployment-stage-dashboard">
        <h2>Code pull / PR</h2>
        {selected.application_type === "GTB-Applications"
          ? <div className="deployment-actions">
              <button className="primary-button" onClick={() => action(selected.id, "trigger-code-pull")}><Play size={15}/>Code pull</button>
              <button className="secondary-button" onClick={() => action(selected.id, "create-pr")}>Raise PR</button>
            </div>
          : <p>This stage is not required for {selected.application_type}.</p>}
      </div>;
    }

    if (activeStage === "Build") {
      return <div className="deployment-stage-dashboard">
        <h2>Build</h2>
        {selected.application_type === "Collections" ? <>
          {!selected.extracted ? <p>Extract the document first.</p> : <>
            <div className="deployment-result-header">
              <div><span className="eyebrow">COLLECTIONS BUILD INPUT REVIEW</span><h3>{selected.country} vendor images</h3></div>
              <strong>{selectedItems.length} selected</strong>
            </div>
            <div className="table-card collections-image-table"><table><thead><tr><th>Select</th><th>Service</th><th>Tag</th><th>useVendorImage</th><th>vendorImage</th><th>Pipeline</th></tr></thead><tbody>
              {(selected.collections_items || []).map((item, index) => <tr key={`${item.service}-${index}`}>
                <td><input type="checkbox" checked={item.selected} disabled={buildLocked} onChange={(event) => updateCollectionItem(index, "selected", event.target.checked)}/></td>
                <td>{item.service}</td>
                <td>{item.image_tag}</td>
                <td><button type="button" className={`vendor-toggle-button ${(item.use_vendor_image ?? true) ? "enabled" : "disabled"}`} disabled={!item.selected || buildLocked} onClick={() => updateCollectionItem(index, "use_vendor_image", !(item.use_vendor_image ?? true))}>{(item.use_vendor_image ?? true) ? "TRUE" : "FALSE"}</button></td>
                <td><input className="collections-vendor-image-input" value={item.vendor_image} disabled={!item.selected || !(item.use_vendor_image ?? true) || buildLocked} onChange={(event) => updateCollectionItem(index, "vendor_image", event.target.value)}/></td>
                <td>{item.pipeline_name || "Mapping missing"}</td>
              </tr>)}
            </tbody></table></div>
            <div className="deployment-actions">
              <button className="secondary-button" disabled={buildLocked} onClick={saveUpdates}>Save reviewed data</button>
              <button className="primary-button" disabled={busy || buildLocked || !collectionsBuildReady} onClick={() => action(selected.id, "trigger-build", { collections_items: selected.collections_items || [] })}>Trigger build</button>
              <button className="secondary-button" onClick={() => action(selected.id, "refresh-status")}><RefreshCw size={15}/>Refresh now</button>
            </div>
          </>}
          <div className="deployment-result-header lifecycle-heading"><h3>Build lifecycle</h3><span className={`status ${statusClass(selected.steps?.build?.status)}`}>{selected.steps?.build?.status || "Waiting"}</span></div>
          {autoRefreshRequired && <p className="auto-refresh-note">Auto-refreshing every 5 seconds.</p>}
          {buildRuns.length === 0 ? <p>No build runs yet.</p> : <div className="table-card lifecycle-table"><table><thead><tr><th>Service</th><th>useVendorImage</th><th>vendorImage</th><th>Pipeline</th><th>Status</th><th>Duration</th><th>Link</th></tr></thead><tbody>
            {buildRuns.map((run, index) => <tr key={`${run.run_id}-${index}`}><td>{run.service}</td><td>{run.use_vendor_image === false ? "FALSE" : "TRUE"}</td><td>{run.vendor_image}</td><td>{run.pipeline_name}</td><td><span className={`status ${statusClass(run.status)}`}>{run.status}</span></td><td>{formatDuration(run.duration_seconds)}</td><td>{run.url ? <a href={run.url} target="_blank" rel="noreferrer">Open</a> : "—"}</td></tr>)}
          </tbody></table></div>}
        </> : <>
          <div className="deployment-form"><label>Build pipeline<input value={selected.build_pipeline || ""} onChange={(event) => updateSelected("build_pipeline", event.target.value)}/></label><label>Branch<input value={selected.branch_name || ""} onChange={(event) => updateSelected("branch_name", event.target.value)}/></label></div>
          <button className="primary-button" onClick={() => action(selected.id, "trigger-build")}>Trigger build</button>
        </>}
      </div>;
    }

    return <div className="deployment-stage-dashboard">
      <h2>Deployment</h2>
      <div className="deployment-actions">
        <button className="primary-button" disabled={selected.application_type === "Collections" && selected.steps?.build?.status !== "Succeeded"} onClick={() => {
          const name = window.prompt("Deployment pipeline name (leave blank to use configured value)");
          void action(selected.id, "trigger-deployment", name ? { pipeline_name: name } : {});
        }}>Trigger deployment</button>
        <button className="secondary-button" onClick={() => action(selected.id, "refresh-status")}><RefreshCw size={15}/>Refresh now</button>
      </div>
      {deploymentRuns.length === 0 ? <p>Deployment has not started.</p> : <div className="table-card lifecycle-table"><table><thead><tr><th>Pipeline</th><th>Status</th><th>Duration</th><th>Link</th><th>Environment</th></tr></thead><tbody>
        {deploymentRuns.map((run, index) => <tr key={`${run.release_id || run.run_id}-${index}`}><td>{run.pipeline_name}</td><td><span className={`status ${statusClass(run.status)}`}>{run.status}</span></td><td>{formatDuration(run.duration_seconds)}</td><td>{run.url ? <a href={run.url} target="_blank" rel="noreferrer">Open</a> : "—"}</td><td>{run.environment_status || selected.country}</td></tr>)}
      </tbody></table></div>}
    </div>;
  }

  return <div className="deployment-management-page">
    <section className="deployment-hero"><div><span className="eyebrow">RELEASE ORCHESTRATION</span><h1>Deployment Management Dashboard</h1><p>Each workflow card opens its own dashboard. The request queue never locks navigation.</p></div><Rocket size={44}/></section>
    <div className="deployment-workflow">{STAGES.map((stage, index) => <button type="button" className={activeStage === stage ? "active" : ""} key={stage} onClick={() => setActiveStage(stage)}><span>{index + 1}</span><strong>{stage}</strong></button>)}</div>

    {role !== "devops" ? <section className="deployment-card developer-release-card">
      <div className="deployment-card-title"><UploadCloud/><div><h2>Submit release document</h2><p>Developers only upload and send for approval.</p></div></div>
      <div className="deployment-form"><label>Application type<select value={appType} onChange={(event) => setAppType(event.target.value)}>{APP_TYPES.map((item) => <option key={item}>{item}</option>)}</select></label>{appType === "Collections" && <label>Country<select value={country} onChange={(event) => setCountry(event.target.value)}>{COLLECTIONS_COUNTRIES.map((item) => <option key={item}>{item}</option>)}</select></label>}<label>Application owner<input value={appOwner} onChange={(event) => setAppOwner(event.target.value)}/></label></div>
      <label className="deployment-upload"><FileText/><input type="file" accept=".pdf,.docx,.txt,.md" onChange={(event) => setFile(event.target.files?.[0] || null)}/><span>{file?.name || "Choose document"}</span></label>
      <button className="primary-button" disabled={!file || !appOwner || busy} onClick={submitDocument}>Send for approval</button>
    </section> : <section className="deployment-grid devops-deployment-grid">
      <article className="deployment-card deployment-queue"><div className="deployment-card-title"><GitPullRequest/><div><h2>Deployment queue</h2><p>Selecting a request does not lock the workflow cards.</p></div></div>{requests.length === 0 ? <div className="monitoring-empty">No requests.</div> : requests.slice(0, 20).map((request) => <button className={`deployment-request deployment-request-button ${selected?.id === request.id ? "selected" : ""}`} key={request.id} onClick={() => setSelected(request)}><div><span>{request.id}</span><h3>{request.application || request.application_type}</h3><p>{request.document_name} · {request.requested_by}{request.country ? ` · ${request.country}` : ""}</p></div><span className={`status ${statusClass(request.status)}`}>{request.status}</span></button>)}</article>
      <article className="deployment-card deployment-orchestrator">{selected?.application_type === "Collections" && <div className="deployment-progress-card"><div><span>Overall progress</span><strong>{selected.progress_percent || 0}%</strong></div><div className="deployment-progress-track"><span style={{ width: `${selected.progress_percent || 0}%` }}/></div></div>}{renderStage()}<label className="deployment-pat">Azure DevOps PAT<input type="password" value={pat} onChange={(event) => setPat(event.target.value)} placeholder="Optional when backend PAT is configured"/></label></article>
    </section>}
    {message && <div className="deployment-message">{message}</div>}
  </div>;
}
