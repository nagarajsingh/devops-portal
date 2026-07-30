import { useEffect, useMemo, useState } from "react";
import {
  approvePipelineRequest,
  closePipelineRequest,
  getIngresses,
  getKubernetesTargets,
  getNamespaces,
  getPipelineRequests,
  getServices,
  rejectPipelineRequest,
  updatePipelineRequest,
} from "../services/api";
import type { KubernetesService, KubernetesTarget, PipelineRequest, ReviewUpdate, Role } from "../types";

interface Props { token: string; role: Role; refreshKey: number; }

const statusClass = (status: string) => {
  const value = status.toLowerCase();
  if (value.includes("complete")) return "healthy";
  if (value.includes("reject") || value.includes("fail") || value.includes("closed")) return "danger-status";
  if (value.includes("provision")) return "progress";
  return "pending";
};

const wait = (milliseconds: number) => new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));

export default function RequestsPage({ token, role, refreshKey }: Props) {
  const [requests, setRequests] = useState<PipelineRequest[]>([]);
  const [selected, setSelected] = useState<PipelineRequest | null>(null);
  const [draft, setDraft] = useState<ReviewUpdate | null>(null);
  const [targets, setTargets] = useState<KubernetesTarget[]>([]);
  const [namespaces, setNamespaces] = useState<string[]>([]);
  const [ingresses, setIngresses] = useState<string[]>([]);
  const [services, setServices] = useState<KubernetesService[]>([]);
  const [azureDevOpsPat, setAzureDevOpsPat] = useState("");
  const [closureComment, setClosureComment] = useState("");
  const [rejectionComment, setRejectionComment] = useState("");
  const [showClosureForm, setShowClosureForm] = useState(false);
  const [showRejectionForm, setShowRejectionForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [loadingIngresses, setLoadingIngresses] = useState(false);
  const [loadingServices, setLoadingServices] = useState(false);
  const [busy, setBusy] = useState(false);
  const [operationStatus, setOperationStatus] = useState("");
  const [operationStep, setOperationStep] = useState(0);
  const [operationTotal, setOperationTotal] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = async () => {
    setLoading(true); setError("");
    try {
      const items = await getPipelineRequests(token);
      setRequests(items);
      if (selected) setSelected(items.find((item) => item.id === selected.id) ?? selected);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load requests");
    } finally { setLoading(false); }
  };

  useEffect(() => { void load(); }, [token, refreshKey]);
  useEffect(() => {
    if (role !== "devops") return;
    getKubernetesTargets(token).then(setTargets).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load Kubernetes targets"));
  }, [role, token]);

  const targetMode = targets.find((item) => item.name === draft?.target_cluster)?.mode ?? (draft?.target_cluster === "local-cluster" ? "direct" : "azure_pipeline");
  const directTarget = targetMode === "direct";

  useEffect(() => {
    if (role !== "devops" || !draft?.target_cluster) return;
    if (!directTarget) { setNamespaces([]); return; }
    getNamespaces(token, draft.target_cluster).then(setNamespaces).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load namespaces"));
  }, [role, token, draft?.target_cluster, directTarget]);

  useEffect(() => {
    if (role !== "devops" || !draft?.namespace || !directTarget) { setIngresses([]); return; }
    setLoadingIngresses(true); setOperationStatus("Loading available ingress resources...");
    getIngresses(draft.namespace, token, draft.target_cluster)
      .then((items) => {
        setIngresses(items);
        setDraft((current) => current ? { ...current, ingress_name: current.ingress_name && items.includes(current.ingress_name) ? current.ingress_name : "" } : current);
      })
      .catch((reason) => { setIngresses([]); setError(reason instanceof Error ? reason.message : "Unable to load ingresses"); })
      .finally(() => setLoadingIngresses(false));
  }, [draft?.namespace, draft?.target_cluster, directTarget, role, token]);

  useEffect(() => {
    if (role !== "devops" || !draft?.namespace || draft.create_service || !directTarget) { setServices([]); return; }
    setLoadingServices(true); setOperationStatus("Loading existing Kubernetes services...");
    getServices(draft.namespace, token, draft.target_cluster)
      .then((items) => {
        setServices(items);
        setDraft((current) => {
          if (!current) return current;
          const service = items.find((item) => item.name === current.service_name);
          return service ? { ...current, service_port: service.ports.includes(current.service_port) ? current.service_port : service.ports[0] ?? current.service_port } : { ...current, service_name: "" };
        });
      })
      .catch((reason) => { setServices([]); setError(reason instanceof Error ? reason.message : "Unable to load services"); })
      .finally(() => setLoadingServices(false));
  }, [draft?.namespace, draft?.create_service, draft?.target_cluster, directTarget, role, token]);

  useEffect(() => {
    if (previewLoading && !loadingIngresses && !loadingServices) { setPreviewLoading(false); setOperationStatus(""); }
  }, [previewLoading, loadingIngresses, loadingServices]);

  const editableStatuses = ["Pending Approval", "Pending Action", "Partially Completed"];
  const closableStatuses = [...editableStatuses, "Completed"];
  const selectedService = services.find((item) => item.name === draft?.service_name);
  const repositoryUrl = selected?.provisioning?.repository?.url;
  const buildPipelineUrl = selected?.provisioning?.pipeline?.url;
  const releasePipelineUrl = selected?.provisioning?.release_pipeline?.url;

  const originalChanges = useMemo(() => {
    if (!selected?.original_request) return [];
    return Object.entries(selected.original_request)
      .filter(([key, value]) => selected[key as keyof PipelineRequest] !== value)
      .map(([key, value]) => ({ key, requested: String(value ?? ""), approved: String(selected[key as keyof PipelineRequest] ?? "") }));
  }, [selected]);

  const openPreview = (request: PipelineRequest) => {
    setOperationStatus("Opening request preview..."); setPreviewLoading(true); setSelected(request); setNotice(""); setError(""); setAzureDevOpsPat("");
    setClosureComment(""); setRejectionComment(""); setShowClosureForm(false); setShowRejectionForm(false);
    setDraft({
      application_type: request.application_type,
      app_owner: request.app_owner,
      repository_name: request.repository_name,
      reference_repository_name: request.reference_repository_name,
      reference_branch: request.reference_branch ?? "",
      setup_pipeline: request.setup_pipeline ?? false,
      pipeline_type: request.pipeline_type,
      ingress_path: request.ingress_path,
      ingress_name: request.ingress_name ?? "",
      create_service: request.create_service,
      service_name: request.service_name || request.repository_name.replace(/_/g, "-"),
      service_port: request.service_port,
      namespace: request.namespace,
      target_cluster: request.target_cluster || "local-cluster",
      comments: request.comments,
      review_comments: request.review_comments,
    });
  };

  const saveChanges = async () => {
    if (!selected || !draft) return;
    setOperationStatus("Saving DevOps changes..."); setOperationStep(1); setOperationTotal(1); setBusy(true); setError("");
    const started = Date.now();
    try { const updated = await updatePipelineRequest(selected.id, draft, token); await wait(Math.max(0, 1000 - (Date.now() - started))); setSelected(updated); setNotice("Request changes saved."); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save changes"); }
    finally { setBusy(false); setOperationStatus(""); setOperationStep(0); setOperationTotal(0); }
  };

  const approve = async () => {
    if (!selected || !draft) return;
    if (!draft.target_cluster) return setError("Select a Kubernetes target before approval.");
    if (!draft.namespace) return setError("Provide a namespace before approval.");
    if (draft.reference_repository_name.trim() && !draft.reference_branch?.trim()) return setError("Provide the reference repository branch before approval.");
    if (draft.setup_pipeline && !draft.reference_repository_name.trim()) return setError("Build and release pipeline setup requires a reference repository.");
    if (!draft.ingress_name) return setError("Provide an ingress resource before approval.");
    if (!draft.service_name.trim()) return setError(draft.create_service ? "Provide the Kubernetes service name." : "Provide the existing Kubernetes service name.");
    if (!azureDevOpsPat.trim()) return setError("Provide your Azure DevOps PAT before approval.");

    const stages = [
      "Saving approved request values...",
      "Checking and creating Azure DevOps repository...",
      draft.reference_repository_name ? "Copying reference repository files..." : "Reference repository not selected; skipping template copy...",
      draft.setup_pipeline ? "Creating Azure DevOps build pipeline..." : "Pipeline setup disabled; skipping build pipeline creation...",
      draft.setup_pipeline ? "Cloning and configuring Azure DevOps release pipeline..." : "Pipeline setup disabled; skipping release pipeline creation...",
      draft.create_service ? "Creating Kubernetes service..." : "Validating existing Kubernetes service...",
      "Updating ingress path...",
      "Finalizing provisioning results...",
    ];

    setBusy(true); setError(""); setNotice(""); setOperationTotal(stages.length);
    const operation = (async () => {
      await updatePipelineRequest(selected.id, draft, token);
      return approvePipelineRequest(selected.id, azureDevOpsPat, token);
    })().then((value) => ({ value, error: null as unknown })).catch((operationError: unknown) => ({ value: null, error: operationError }));

    try {
      for (let index = 0; index < stages.length; index += 1) {
        setOperationStep(index + 1); setOperationStatus(stages[index]); await wait(1000);
      }
      const result = await operation;
      if (result.error) throw result.error;
      const updated = result.value as PipelineRequest;
      setAzureDevOpsPat(""); setSelected(updated); setNotice(`Provisioning finished with status: ${updated.status}. Review and close the ticket.`); await load();
    } catch (reason) {
      setAzureDevOpsPat(""); setError(reason instanceof Error ? reason.message : "Approval failed"); await load();
    } finally { setBusy(false); setOperationStatus(""); setOperationStep(0); setOperationTotal(0); }
  };

  const reject = async () => {
    if (!selected) return;
    const reason = rejectionComment.trim();
    if (!reason) return setError("Rejection comment is mandatory.");
    setBusy(true); setOperationStatus("Rejecting request..."); setOperationStep(1); setOperationTotal(1); setError("");
    const started = Date.now();
    try { const updated = await rejectPipelineRequest(selected.id, reason, token); await wait(Math.max(0, 1000 - (Date.now() - started))); setSelected(updated); setShowRejectionForm(false); setRejectionComment(""); setNotice("Request rejected with the provided comment."); await load(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to reject request"); }
    finally { setBusy(false); setOperationStatus(""); setOperationStep(0); setOperationTotal(0); }
  };

  const closeTicket = async () => {
    if (!selected || !closureComment.trim()) return setError("Closure comment is mandatory.");
    setBusy(true); setOperationStatus("Closing ticket and publishing provisioning details..."); setOperationStep(1); setOperationTotal(1); setError("");
    const started = Date.now();
    try { const updated = await closePipelineRequest(selected.id, closureComment.trim(), token); await wait(Math.max(0, 1000 - (Date.now() - started))); setSelected(updated); setShowClosureForm(false); setClosureComment(""); setNotice("Ticket closed and visible to the developer."); await load(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to close ticket"); }
    finally { setBusy(false); setOperationStatus(""); setOperationStep(0); setOperationTotal(0); }
  };

  return <section>
    {(busy || previewLoading) && <div className="operation-overlay"><div className="loading-spinner"/><strong>{operationStatus || "Processing request..."}</strong>{operationTotal > 0 && <><div className="operation-progress-meta"><span>Step {operationStep} of {operationTotal}</span><span>{Math.round((operationStep / operationTotal) * 100)}%</span></div><div className="operation-progress-track"><span style={{ width: `${(operationStep / operationTotal) * 100}%` }} /></div></>}<span>Please wait. Do not refresh or close this page.</span></div>}
    <div className="section-heading"><div><span className="eyebrow">PIPELINE ONBOARDING</span><h2>{role === "devops" ? "DevOps Provisioning Queue" : "My Pipeline Requests"}</h2><p>{role === "devops" ? "Only app-owner-approved requests are displayed here." : "Track app-owner approval, DevOps provisioning and closure details."}</p></div></div>
    <div className="table-card">{loading ? <p>Loading requests...</p> : error && !selected ? <div className="form-error">{error}</div> : requests.length === 0 ? <p>No requests are available.</p> : <table><thead><tr><th>Request ID</th><th>Application</th><th>App Owner</th><th>Repository</th><th>Namespace</th><th>Status</th><th>Action</th></tr></thead><tbody>{requests.map((request) => <tr key={request.id}><td><strong>{request.id}</strong></td><td>{request.application_type}</td><td>{request.app_owner}</td><td>{request.repository_name}</td><td>{request.namespace || "Assigned by DevOps"}</td><td><span className={`status ${statusClass(request.status)}`}>{request.status}</span></td><td><button className="secondary-button compact-button" onClick={() => openPreview(request)}>Preview</button></td></tr>)}</tbody></table>}</div>

    {selected && draft && <div className="request-modal-backdrop" onClick={() => !busy && setSelected(null)}><article className="request-modal" onClick={(event) => event.stopPropagation()}>
      <div className="modal-header"><div><span className="request-id">{selected.id}</span><h2>{selected.repository_name}</h2><p>Submitted by {selected.requested_by} on {new Date(selected.created_at).toLocaleString()}</p></div><button className="secondary-button" disabled={busy} onClick={() => setSelected(null)}>Close</button></div>
      {error && <div className="form-error">{error}</div>}{notice && <div className="form-success">{notice}</div>}
      <div className="request-status-row"><span className={`status ${statusClass(selected.status)}`}>{selected.status}</span><span>App owner: {selected.app_owner}</span>{selected.app_owner_decision_by && <span>Decision by {selected.app_owner_decision_by}</span>}</div>
      <div className="form-card two-column review-form">
        <label>Application<input disabled value={draft.application_type}/></label>
        <label>Application Owner<input disabled value={draft.app_owner}/></label>
        <label>Repository Name<input disabled={role !== "devops"} value={draft.repository_name} onChange={(e) => setDraft({...draft, repository_name:e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "")})}/></label>
        <label>Type of Language<input disabled value={draft.pipeline_type ?? "Not selected"}/></label>
        <label>Reference Repository (Optional)<input disabled={role !== "devops"} value={draft.reference_repository_name} onChange={(e) => setDraft({...draft, reference_repository_name:e.target.value})}/></label>
        <label>Ingress Path<input disabled={role !== "devops"} value={draft.ingress_path} onChange={(e) => setDraft({...draft, ingress_path:e.target.value})}/></label>
        <label>Service Port<input disabled={role !== "devops"} type="number" value={draft.service_port} onChange={(e) => setDraft({...draft, service_port:Number(e.target.value)})}/></label>
        {role === "devops" && <>
          <label>Target Kubernetes Cluster<select value={draft.target_cluster} onChange={(e) => setDraft({...draft, target_cluster:e.target.value, namespace:"", ingress_name:"", service_name:draft.create_service?draft.repository_name.replace(/_/g,"-"):""})}><option value="">Select target cluster</option>{targets.map((target)=><option key={target.name} value={target.name}>{target.name}</option>)}</select><small>The portal automatically uses direct access or the provisioning pipeline.</small></label>
          {directTarget ? <label>Namespace<select value={draft.namespace} onChange={(e) => setDraft({...draft, namespace:e.target.value, ingress_name:"", service_name:draft.create_service?draft.repository_name.replace(/_/g,"-"):""})}><option value="">Select namespace</option>{namespaces.map((name)=><option key={name} value={name}>{name}</option>)}</select></label> : <label>Namespace<input value={draft.namespace} placeholder="mobile-orchestration-sit" onChange={(e)=>setDraft({...draft,namespace:e.target.value.toLowerCase(),ingress_name:""})}/></label>}
          <label>Build & Release Pipeline Setup<select value={String(draft.setup_pipeline)} onChange={(e) => setDraft({...draft, setup_pipeline:e.target.value==="true"})}><option value="true">Yes</option><option value="false">No</option></select></label>
          <label>Reference Branch<input disabled={!draft.reference_repository_name.trim()} value={draft.reference_branch ?? ""} placeholder={draft.application_type === "Native-Mobile" ? "develop" : "release/uat"} onChange={(e) => setDraft({...draft, reference_branch:e.target.value.trim()})}/></label>
          {directTarget ? <label>Ingress Resource<select value={draft.ingress_name ?? ""} disabled={!draft.namespace || loadingIngresses} onChange={(e) => setDraft({...draft, ingress_name:e.target.value})}><option value="">{loadingIngresses?"Loading ingresses...":"Select ingress"}</option>{ingresses.map((name)=><option key={name} value={name}>{name}</option>)}</select></label> : <label>Ingress Resource<input value={draft.ingress_name ?? ""} placeholder="existing-ingress-name" onChange={(e)=>setDraft({...draft,ingress_name:e.target.value.toLowerCase()})}/></label>}
          <label className="checkbox-line"><input type="checkbox" checked={draft.create_service} onChange={(e) => setDraft({...draft, create_service:e.target.checked, service_name:e.target.checked?draft.repository_name.replace(/_/g,"-"):""})}/>Create Kubernetes Service</label>
          {draft.create_service ? <label>Service Name<input value={draft.service_name} onChange={(e) => setDraft({...draft, service_name:e.target.value.replace(/_/g,"-")})}/></label> : directTarget ? <label>Existing Service<select value={draft.service_name} disabled={!draft.namespace || loadingServices} onChange={(e)=>{const service=services.find((item)=>item.name===e.target.value);setDraft({...draft,service_name:e.target.value,service_port:service?.ports[0]??draft.service_port});}}><option value="">{loadingServices?"Loading services...":"Select existing service"}</option>{services.map((service)=><option key={service.name} value={service.name}>{service.name}</option>)}</select></label> : <label>Existing Service<input value={draft.service_name} placeholder="existing-service-name" onChange={(e)=>setDraft({...draft,service_name:e.target.value.replace(/_/g,"-")})}/></label>}
          {!draft.create_service && directTarget && selectedService?.ports.length ? <label>Existing Service Port<select value={draft.service_port} onChange={(e)=>setDraft({...draft,service_port:Number(e.target.value)})}>{selectedService.ports.map((port)=><option key={port}>{port}</option>)}</select></label> : null}
          {editableStatuses.includes(selected.status) && <label className="full-width">Azure DevOps PAT<input type="password" autoComplete="new-password" value={azureDevOpsPat} placeholder="PAT is used once and never stored" onChange={(e)=>setAzureDevOpsPat(e.target.value)}/></label>}
        </>}
        <label className="full-width">Developer Comments<textarea disabled rows={3} value={draft.comments ?? ""}/></label>
        {role === "devops" && <label className="full-width">DevOps Review Comments<textarea disabled={!editableStatuses.includes(selected.status)} rows={3} value={draft.review_comments ?? ""} onChange={(e)=>setDraft({...draft,review_comments:e.target.value})}/></label>}
      </div>

      {showRejectionForm && role === "devops" && editableStatuses.includes(selected.status) && <div className="ticket-closure-form rejection-form"><div><span className="eyebrow">REJECTION REVIEW</span><h3>Reject this request</h3><p>The mandatory rejection comment will be recorded in the timeline and visible to the developer.</p></div><label>Mandatory rejection comment<textarea autoFocus rows={4} maxLength={1000} value={rejectionComment} placeholder="Explain why this request is being rejected." onChange={(e)=>setRejectionComment(e.target.value)}/><small>{rejectionComment.trim().length}/1000 characters</small></label><div className="ticket-closure-actions"><button className="secondary-button" onClick={()=>{setShowRejectionForm(false);setRejectionComment("");setError("");}}>Cancel</button><button className="danger-button" disabled={!rejectionComment.trim()||busy} onClick={reject}>Confirm & Reject Request</button></div></div>}
      {showClosureForm && role === "devops" && <div className="ticket-closure-form"><div><span className="eyebrow">FINAL REVIEW</span><h3>Close this ticket</h3><p>The comment and resource URLs will be visible to the developer.</p></div><label>Mandatory closure comment<textarea autoFocus rows={4} maxLength={1000} value={closureComment} onChange={(e)=>setClosureComment(e.target.value)}/><small>{closureComment.trim().length}/1000 characters</small></label><div className="ticket-closure-actions"><button className="secondary-button" onClick={()=>{setShowClosureForm(false);setClosureComment("");}}>Cancel</button><button className="primary-button" disabled={!closureComment.trim()||busy} onClick={closeTicket}>Confirm & Close Ticket</button></div></div>}
      {selected.status === "Closed" && <div className="closure-summary"><h3>Provisioning Completed and Ticket Closed</h3><p><strong>DevOps closure comment:</strong> {selected.closure_comment}</p><div className="resource-links"><div><span>Repository</span>{repositoryUrl?<a href={repositoryUrl} target="_blank" rel="noreferrer">Open repository</a>:<strong>Not created or unavailable</strong>}</div><div><span>Build Pipeline</span>{buildPipelineUrl?<a href={buildPipelineUrl} target="_blank" rel="noreferrer">Open build pipeline</a>:<strong>Not created or skipped</strong>}</div><div><span>Release Pipeline</span>{releasePipelineUrl?<a href={releasePipelineUrl} target="_blank" rel="noreferrer">Open release pipeline</a>:<strong>Not created or skipped</strong>}</div></div></div>}
      {originalChanges.length>0&&<div className="change-summary"><h3>Changes made by DevOps</h3>{originalChanges.map((change)=><div key={change.key}><strong>{change.key.replace(/_/g," ")}</strong><span>{change.requested}</span><span>→</span><span>{change.approved}</span></div>)}</div>}
      {selected.provisioning&&Object.keys(selected.provisioning).length>0&&<div className="provision-grid"><h3>Provisioning Status</h3>{Object.entries(selected.provisioning).map(([name,step])=><div className="provision-step" key={name}><strong>{name.replace(/_/g, " ")}</strong><span className={`status ${statusClass(step.status)}`}>{step.status}</span><small>{step.message}</small>{step.url&&<a href={step.url} target="_blank" rel="noreferrer">Open resource</a>}</div>)}</div>}
      {selected.timeline&&selected.timeline.length>0&&<div className="timeline"><h3>Timeline</h3>{selected.timeline.map((event,index)=><div key={`${event.at}-${index}`}><strong>{event.action}</strong><span>{event.actor} · {new Date(event.at).toLocaleString()}</span><small>{event.detail}</small></div>)}</div>}
      {role==="devops"&&closableStatuses.includes(selected.status)&&!showClosureForm&&!showRejectionForm&&<div className="modal-actions">{editableStatuses.includes(selected.status)&&<><button disabled={busy} className="secondary-button" onClick={saveChanges}>Save Changes</button><button disabled={busy} className="danger-button" onClick={()=>{setError("");setNotice("");setRejectionComment("");setShowRejectionForm(true);}}>Reject</button><button disabled={busy} className="primary-button" onClick={approve}>Approve & Provision</button></>}<button disabled={busy} className="secondary-button close-ticket-button" onClick={()=>{setError("");setNotice("");setClosureComment("");setShowClosureForm(true);}}>Close Ticket</button></div>}
    </article></div>}
  </section>;
}
