import { useEffect, useMemo, useState } from "react";
import { approvePipelineRequest, closePipelineRequest, getIngresses, getPipelineRequests, getServices, rejectPipelineRequest, updatePipelineRequest } from "../services/api";
import type { KubernetesService, PipelineRequest, ReviewUpdate, Role } from "../types";

interface Props { token: string; role: Role; refreshKey: number; }
const statusClass = (status: string) => { const value = status.toLowerCase(); if (value.includes("complete")) return "healthy"; if (value.includes("reject") || value.includes("fail") || value.includes("closed")) return "danger-status"; if (value.includes("provision")) return "progress"; return "pending"; };

export default function RequestsPage({ token, role, refreshKey }: Props) {
  const [requests, setRequests] = useState<PipelineRequest[]>([]);
  const [selected, setSelected] = useState<PipelineRequest | null>(null);
  const [draft, setDraft] = useState<ReviewUpdate | null>(null);
  const [azureDevOpsPat, setAzureDevOpsPat] = useState("");
  const [ingresses, setIngresses] = useState<string[]>([]);
  const [services, setServices] = useState<KubernetesService[]>([]);
  const [loadingIngresses, setLoadingIngresses] = useState(false);
  const [loadingServices, setLoadingServices] = useState(false);
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [operationStatus, setOperationStatus] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = async () => { setLoading(true); setError(""); try { const items = await getPipelineRequests(token); setRequests(items); if (selected) setSelected(items.find((item) => item.id === selected.id) ?? null); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load requests"); } finally { setLoading(false); } };
  useEffect(() => { void load(); }, [token, refreshKey]);

  useEffect(() => {
    if (role !== "devops" || !draft?.namespace) return;
    setOperationStatus("Loading available ingress resources...");
    setLoadingIngresses(true);
    getIngresses(draft.namespace, token).then((items) => { setIngresses(items); setDraft((current) => current ? { ...current, ingress_name: current.ingress_name && items.includes(current.ingress_name) ? current.ingress_name : "" } : current); }).catch((reason) => { setIngresses([]); setError(reason instanceof Error ? reason.message : "Unable to load ingresses"); }).finally(() => setLoadingIngresses(false));
  }, [draft?.namespace, role, token]);

  useEffect(() => {
    if (role !== "devops" || !draft?.namespace || draft.create_service) return;
    setOperationStatus("Loading existing Kubernetes services...");
    setLoadingServices(true);
    getServices(draft.namespace, token).then((items) => { setServices(items); setDraft((current) => { if (!current) return current; const service = items.find((item) => item.name === current.service_name); if (service) return { ...current, service_port: service.ports.includes(current.service_port) ? current.service_port : service.ports[0] ?? current.service_port }; return { ...current, service_name: "" }; }); }).catch((reason) => { setServices([]); setError(reason instanceof Error ? reason.message : "Unable to load services"); }).finally(() => setLoadingServices(false));
  }, [draft?.namespace, draft?.create_service, role, token]);

  useEffect(() => { if (previewLoading && !loadingIngresses && !loadingServices) { setPreviewLoading(false); setOperationStatus(""); } }, [previewLoading, loadingIngresses, loadingServices]);

  const originalChanges = useMemo(() => { if (!selected?.original_request) return []; return Object.entries(selected.original_request).filter(([key, value]) => selected[key as keyof PipelineRequest] !== value).map(([key, value]) => ({ key, requested: String(value ?? ""), approved: String(selected[key as keyof PipelineRequest] ?? "") })); }, [selected]);

  const openPreview = (request: PipelineRequest) => {
    setOperationStatus("Opening request preview..."); setPreviewLoading(true); setSelected(request); setNotice(""); setError(""); setAzureDevOpsPat("");
    setDraft({ application_type: request.application_type, repository_name: request.repository_name, reference_repository_name: request.reference_repository_name, reference_branch: request.reference_branch ?? "", setup_pipeline: request.setup_pipeline ?? Boolean(request.reference_repository_name), pipeline_type: request.pipeline_type, ingress_path: request.ingress_path, ingress_name: request.ingress_name ?? "", create_service: request.create_service, service_name: request.service_name, service_port: request.service_port, namespace: request.namespace, comments: request.comments, review_comments: request.review_comments });
  };

  const saveChanges = async () => { if (!selected || !draft) return; setOperationStatus("Saving DevOps changes..."); setBusy(true); setError(""); try { const updated = await updatePipelineRequest(selected.id, draft, token); setSelected(updated); setNotice("Request changes saved."); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save changes"); } finally { setBusy(false); setOperationStatus(""); } };

  const approve = async () => {
    if (!selected || !draft) return;
    if (draft.reference_repository_name.trim() && !draft.reference_branch?.trim()) { setError("Provide the reference repository branch before approval."); return; }
    if (draft.setup_pipeline && !draft.reference_repository_name.trim()) { setError("Pipeline setup requires a reference repository."); return; }
    if (!draft.ingress_name) { setError("Select an ingress from the requested namespace before approval."); return; }
    if (!draft.service_name.trim()) { setError(draft.create_service ? "Provide the Kubernetes service name." : "Select an existing Kubernetes service."); return; }
    if (!azureDevOpsPat.trim()) { setError("Provide your Azure DevOps PAT before approval."); return; }

    const stages = [
      "Saving approved request values...",
      "Checking and creating Azure DevOps repository...",
      draft.reference_repository_name.trim() ? "Creating or updating feature/devops branch and copying template files..." : "Reference repository not selected; skipping template copy...",
      draft.setup_pipeline ? "Creating Azure DevOps build pipeline..." : "Pipeline setup disabled; skipping pipeline creation...",
      draft.create_service ? "Creating Kubernetes service..." : "Validating selected Kubernetes service...",
      "Updating ingress path...",
      "Finalizing provisioning results...",
    ];
    let stageIndex = 0;
    setOperationStatus(stages[stageIndex]);
    const stageTimer = window.setInterval(() => { stageIndex = Math.min(stageIndex + 1, stages.length - 1); setOperationStatus(stages[stageIndex]); }, 1800);

    setBusy(true); setError(""); setNotice("");
    try { await updatePipelineRequest(selected.id, draft, token); const updated = await approvePipelineRequest(selected.id, azureDevOpsPat, token); setAzureDevOpsPat(""); setSelected(updated); setNotice(`Provisioning finished with status: ${updated.status}. Review the results and close the ticket with a mandatory comment.`); await load(); }
    catch (reason) { setAzureDevOpsPat(""); const message = reason instanceof Error ? reason.message : "Approval failed"; setError(message.includes("already exists") ? `${message}. Rename the repository and save before approving again.` : message); await load(); }
    finally { window.clearInterval(stageTimer); setBusy(false); setOperationStatus(""); }
  };

  const reject = async () => { if (!selected) return; const reason = window.prompt("Provide rejection reason"); if (!reason) return; setOperationStatus("Rejecting request..."); setBusy(true); try { const updated = await rejectPipelineRequest(selected.id, reason, token); setSelected(updated); setNotice("Request rejected."); await load(); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to reject request"); } finally { setBusy(false); setOperationStatus(""); } };
  const closeTicket = async () => { if (!selected) return; const comment = window.prompt("Mandatory closure comment"); if (!comment?.trim()) { setError("Closure comment is mandatory."); return; } setOperationStatus("Closing ticket and publishing provisioning details..."); setBusy(true); try { const updated = await closePipelineRequest(selected.id, comment.trim(), token); setSelected(updated); setNotice("Ticket closed. Repository and pipeline details are now visible to the developer."); await load(); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to close ticket"); } finally { setBusy(false); setOperationStatus(""); } };
  const selectedService = services.find((item) => item.name === draft?.service_name);
  const repositoryUrl = selected?.provisioning?.repository?.url;
  const pipelineUrl = selected?.provisioning?.pipeline?.url;
  const editableStatuses = ["Pending Approval", "Pending Action", "Partially Completed"];
  const closableStatuses = [...editableStatuses, "Completed"];

  return <section>
    {(busy || previewLoading) && <div className="operation-overlay"><div className="loading-spinner"/><strong>{operationStatus || (busy ? "Processing request..." : "Loading preview...")}</strong><span>Please wait. Do not refresh or close this page.</span></div>}
    <div className="section-heading"><div><span className="eyebrow">PIPELINE ONBOARDING</span><h2>{role === "devops" ? "All Pipeline Requests" : "My Pipeline Requests"}</h2><p>Preview approved values, provisioning progress and pending actions.</p></div></div>
    <div className="table-card">{loading ? <p>Loading requests...</p> : error && !selected ? <div className="form-error">{error}</div> : requests.length === 0 ? <p>No requests have been submitted yet.</p> : <table><thead><tr><th>Request ID</th><th>Application</th><th>Repository</th><th>Pipeline</th><th>Namespace</th><th>Status</th><th>Action</th></tr></thead><tbody>{requests.map((request) => <tr key={request.id}><td><strong>{request.id}</strong></td><td>{request.application_type}</td><td>{request.repository_name}</td><td>{request.setup_pipeline ? "Yes" : "No"}</td><td>{request.namespace}</td><td><span className={`status ${statusClass(request.status)}`}>{request.status}</span></td><td><button className="secondary-button compact-button" onClick={() => openPreview(request)}>Preview</button></td></tr>)}</tbody></table>}</div>

    {selected && draft && <div className="request-modal-backdrop" onClick={() => !busy && setSelected(null)}><article className="request-modal" onClick={(event) => event.stopPropagation()}>
      <div className="modal-header"><div><span className="request-id">{selected.id}</span><h2>{selected.repository_name}</h2><p>Submitted by {selected.requested_by} on {new Date(selected.created_at).toLocaleString()}</p></div><button className="secondary-button" disabled={busy} onClick={() => setSelected(null)}>Close</button></div>
      {error && <div className="form-error">{error}</div>}{notice && <div className="form-success">{notice}</div>}
      <div className="request-status-row"><span className={`status ${statusClass(selected.status)}`}>{selected.status}</span>{selected.reviewed_by && <span>Reviewed by {selected.reviewed_by}</span>}</div>
      <div className="form-card two-column review-form">
        <label>Application<input disabled value={draft.application_type} /></label>
        <label>Repository Name<input disabled={role !== "devops"} value={draft.repository_name} onChange={(e) => setDraft({ ...draft, repository_name: e.target.value })} /></label>
        <label>Reference Repository (Optional)<input disabled={role !== "devops"} value={draft.reference_repository_name} onChange={(e) => { const value=e.target.value; setDraft({ ...draft, reference_repository_name:value, setup_pipeline:value.trim()?true:false, reference_branch:value.trim()?draft.reference_branch:"" }); }} /></label>
        <label>Reference Branch<input disabled={role !== "devops" || !draft.reference_repository_name.trim()} required={Boolean(draft.reference_repository_name.trim())} value={draft.reference_branch ?? ""} placeholder="release/uat" onChange={(e) => setDraft({ ...draft, reference_branch: e.target.value.trim() })} /></label>
        <label>Pipeline Setup<select disabled={role !== "devops"} value={String(draft.setup_pipeline)} onChange={(e) => setDraft({ ...draft, setup_pipeline:e.target.value === "true" })}><option value="true">Yes</option><option value="false">No</option></select></label>
        <label>Pipeline Type<input disabled={role !== "devops"} value={draft.pipeline_type ?? ""} onChange={(e) => setDraft({ ...draft, pipeline_type: e.target.value })} /></label>
        <label>Namespace<input disabled value={draft.namespace} /></label>
        <label>Ingress Path<input disabled={role !== "devops"} value={draft.ingress_path} onChange={(e) => setDraft({ ...draft, ingress_path: e.target.value })} /></label>
        <label>Ingress Resource{role === "devops" ? <select required value={draft.ingress_name ?? ""} disabled={loadingIngresses} onChange={(e) => setDraft({ ...draft, ingress_name: e.target.value })}><option value="">{loadingIngresses ? "Loading ingresses..." : "Select ingress"}</option>{ingresses.map((name) => <option key={name} value={name}>{name}</option>)}</select> : <input disabled value={draft.ingress_name || "Not selected"} />}</label>
        {draft.create_service ? <label>Service Name<input disabled={role !== "devops"} value={draft.service_name} onChange={(e) => setDraft({ ...draft, service_name: e.target.value })} /></label> : <label>Existing Service{role === "devops" ? <select required value={draft.service_name} disabled={loadingServices} onChange={(e) => { const service=services.find((item)=>item.name===e.target.value); setDraft({ ...draft, service_name:e.target.value, service_port:service?.ports[0]??draft.service_port }); }}><option value="">{loadingServices ? "Loading services..." : "Select existing service"}</option>{services.map((service)=><option key={service.name} value={service.name}>{service.name}</option>)}</select> : <input disabled value={draft.service_name || "Not selected"} />}</label>}
        <label>Service Port{!draft.create_service && role === "devops" && selectedService?.ports.length ? <select value={draft.service_port} onChange={(e) => setDraft({ ...draft, service_port:Number(e.target.value) })}>{selectedService.ports.map((port)=><option key={port} value={port}>{port}</option>)}</select> : <input disabled={role !== "devops"} type="number" value={draft.service_port} onChange={(e) => setDraft({ ...draft, service_port:Number(e.target.value) })} />}</label>
        <label className="checkbox-line"><input disabled={role !== "devops"} type="checkbox" checked={draft.create_service} onChange={(e) => setDraft({ ...draft, create_service:e.target.checked, service_name:e.target.checked?draft.repository_name:"" })} />Create Kubernetes Service</label>
        {role === "devops" && editableStatuses.includes(selected.status) && <label className="full-width">Azure DevOps PAT<input type="password" autoComplete="new-password" value={azureDevOpsPat} placeholder="PAT is used once and is never stored" onChange={(e) => setAzureDevOpsPat(e.target.value)} /><small>Required only when approving.</small></label>}
        <label className="full-width">Developer Comments<textarea disabled rows={3} value={draft.comments ?? ""} /></label>
        <label className="full-width">DevOps Review Comments<textarea disabled={role !== "devops" || !editableStatuses.includes(selected.status)} rows={3} value={draft.review_comments ?? ""} onChange={(e) => setDraft({ ...draft, review_comments:e.target.value })} /></label>
      </div>
      {selected.status === "Closed" && <div className="closure-summary"><h3>Provisioning Completed and Ticket Closed</h3><p><strong>DevOps closure comment:</strong> {selected.closure_comment}</p><div className="resource-links"><div><span>Repository</span>{repositoryUrl ? <a href={repositoryUrl} target="_blank" rel="noreferrer">Open repository</a> : <strong>Not created or unavailable</strong>}</div><div><span>Build Pipeline</span>{pipelineUrl ? <a href={pipelineUrl} target="_blank" rel="noreferrer">Open pipeline</a> : <strong>Not created or skipped</strong>}</div></div></div>}
      {originalChanges.length > 0 && <div className="change-summary"><h3>Changes made by DevOps</h3>{originalChanges.map((change)=><div key={change.key}><strong>{change.key.replace(/_/g," ")}</strong><span>{change.requested}</span><span>→</span><span>{change.approved}</span></div>)}</div>}
      {selected.provisioning && Object.keys(selected.provisioning).length > 0 && <div className="provision-grid"><h3>Provisioning Status</h3>{Object.entries(selected.provisioning).map(([name,step])=><div className="provision-step" key={name}><strong>{name}</strong><span className={`status ${statusClass(step.status)}`}>{step.status}</span><small>{step.message}</small>{step.url&&<a href={step.url} target="_blank" rel="noreferrer">Open resource</a>}</div>)}</div>}
      {selected.timeline && selected.timeline.length > 0 && <div className="timeline"><h3>Timeline</h3>{selected.timeline.map((event,index)=><div key={`${event.at}-${index}`}><strong>{event.action}</strong><span>{event.actor} · {new Date(event.at).toLocaleString()}</span><small>{event.detail}</small></div>)}</div>}
      {role === "devops" && closableStatuses.includes(selected.status) && <div className="modal-actions">{editableStatuses.includes(selected.status) && <><button disabled={busy} className="secondary-button" onClick={saveChanges}>Save Changes</button><button disabled={busy} className="danger-button" onClick={reject}>Reject</button><button disabled={busy} className="primary-button" onClick={approve}>Approve & Provision</button></>}<button disabled={busy} className="secondary-button" onClick={closeTicket}>Close Ticket</button></div>}
    </article></div>}
  </section>;
}
