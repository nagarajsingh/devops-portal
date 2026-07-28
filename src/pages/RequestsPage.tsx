import { useEffect, useMemo, useState } from "react";
import {
  approvePipelineRequest,
  getPipelineRequests,
  rejectPipelineRequest,
  updatePipelineRequest,
} from "../services/api";
import type { PipelineRequest, ReviewUpdate, Role } from "../types";

interface Props {
  token: string;
  role: Role;
  refreshKey: number;
}

const statusClass = (status: string) => {
  const value = status.toLowerCase();
  if (value.includes("complete")) return "healthy";
  if (value.includes("reject") || value.includes("fail")) return "danger-status";
  if (value.includes("provision")) return "progress";
  return "pending";
};

export default function RequestsPage({ token, role, refreshKey }: Props) {
  const [requests, setRequests] = useState<PipelineRequest[]>([]);
  const [selected, setSelected] = useState<PipelineRequest | null>(null);
  const [draft, setDraft] = useState<ReviewUpdate | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const items = await getPipelineRequests(token);
      setRequests(items);
      if (selected) {
        setSelected(items.find((item) => item.id === selected.id) ?? null);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load requests");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [token, refreshKey]);

  const originalChanges = useMemo(() => {
    if (!selected?.original_request) return [];
    return Object.entries(selected.original_request)
      .filter(([key, value]) => selected[key as keyof PipelineRequest] !== value)
      .map(([key, value]) => ({ key, requested: String(value ?? ""), approved: String(selected[key as keyof PipelineRequest] ?? "") }));
  }, [selected]);

  const openPreview = (request: PipelineRequest) => {
    setSelected(request);
    setNotice("");
    setError("");
    setDraft({
      application_name: request.application_name,
      repository_name: request.repository_name,
      pipeline_type: request.pipeline_type,
      ingress_path: request.ingress_path,
      create_service: request.create_service,
      service_name: request.service_name,
      service_port: request.service_port,
      namespace: request.namespace,
      comments: request.comments,
      review_comments: request.review_comments,
    });
  };

  const saveChanges = async () => {
    if (!selected || !draft) return;
    setBusy(true);
    setError("");
    try {
      const updated = await updatePipelineRequest(selected.id, draft, token);
      setSelected(updated);
      setNotice("Request changes saved. The developer will see the approved values.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save changes");
    } finally {
      setBusy(false);
    }
  };

  const approve = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (draft) await updatePipelineRequest(selected.id, draft, token);
      const updated = await approvePipelineRequest(selected.id, token);
      setSelected(updated);
      setNotice(`Provisioning finished with status: ${updated.status}`);
      await load();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Approval failed";
      setError(message.includes("already exists") ? `${message}. Rename the repository and save before approving again.` : message);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!selected) return;
    const reason = window.prompt("Provide rejection reason");
    if (!reason) return;
    setBusy(true);
    try {
      const updated = await rejectPipelineRequest(selected.id, reason, token);
      setSelected(updated);
      setNotice("Request rejected and status updated for the developer.");
      await load();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to reject request");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <div className="section-heading">
        <div>
          <span className="eyebrow">PIPELINE ONBOARDING</span>
          <h2>{role === "devops" ? "All Pipeline Requests" : "My Pipeline Requests"}</h2>
          <p>Preview approved values, provisioning progress and pending actions.</p>
        </div>
      </div>

      <div className="table-card">
        {loading ? <p>Loading requests...</p> : error && !selected ? <div className="form-error">{error}</div> : requests.length === 0 ? <p>No requests have been submitted yet.</p> : (
          <table>
            <thead><tr><th>Request ID</th><th>Application</th><th>Repository</th><th>Namespace</th><th>Service</th><th>Status</th><th>Requested By</th><th>Action</th></tr></thead>
            <tbody>{requests.map((request) => (
              <tr key={request.id}>
                <td><strong>{request.id}</strong></td>
                <td>{request.application_name}</td>
                <td>{request.repository_name}</td>
                <td>{request.namespace}</td>
                <td>{request.create_service ? `${request.service_name}:${request.service_port}` : "Not requested"}</td>
                <td><span className={`status ${statusClass(request.status)}`}>{request.status}</span></td>
                <td>{request.requested_by}</td>
                <td><button className="secondary-button compact-button" onClick={() => openPreview(request)}>Preview</button></td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </div>

      {selected && draft && (
        <div className="request-modal-backdrop" onClick={() => setSelected(null)}>
          <article className="request-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div><span className="request-id">{selected.id}</span><h2>{selected.application_name}</h2><p>Submitted by {selected.requested_by} on {new Date(selected.created_at).toLocaleString()}</p></div>
              <button className="secondary-button" onClick={() => setSelected(null)}>Close</button>
            </div>

            {error && <div className="form-error">{error}</div>}
            {notice && <div className="form-success">{notice}</div>}

            <div className="request-status-row"><span className={`status ${statusClass(selected.status)}`}>{selected.status}</span>{selected.reviewed_by && <span>Reviewed by {selected.reviewed_by}</span>}</div>

            <div className="form-card two-column review-form">
              <label>Application Name<input disabled={role !== "devops"} value={draft.application_name} onChange={(e) => setDraft({ ...draft, application_name: e.target.value })} /></label>
              <label>Repository Name<input disabled={role !== "devops"} value={draft.repository_name} onChange={(e) => setDraft({ ...draft, repository_name: e.target.value })} /></label>
              <label>Pipeline Type<input disabled={role !== "devops"} value={draft.pipeline_type ?? ""} onChange={(e) => setDraft({ ...draft, pipeline_type: e.target.value })} /></label>
              <label>Namespace<input disabled={role !== "devops"} value={draft.namespace} onChange={(e) => setDraft({ ...draft, namespace: e.target.value })} /></label>
              <label>Ingress Path<input disabled={role !== "devops"} value={draft.ingress_path} onChange={(e) => setDraft({ ...draft, ingress_path: e.target.value })} /></label>
              <label>Service Name<input disabled={role !== "devops" || !draft.create_service} value={draft.service_name} onChange={(e) => setDraft({ ...draft, service_name: e.target.value })} /></label>
              <label>Service Port<input disabled={role !== "devops" || !draft.create_service} type="number" value={draft.service_port} onChange={(e) => setDraft({ ...draft, service_port: Number(e.target.value) })} /></label>
              <label className="checkbox-line"><input disabled={role !== "devops"} type="checkbox" checked={draft.create_service} onChange={(e) => setDraft({ ...draft, create_service: e.target.checked })} />Create Kubernetes Service</label>
              <label className="full-width">Developer Comments<textarea disabled rows={3} value={draft.comments ?? ""} /></label>
              <label className="full-width">DevOps Review Comments<textarea disabled={role !== "devops"} rows={3} value={draft.review_comments ?? ""} onChange={(e) => setDraft({ ...draft, review_comments: e.target.value })} /></label>
            </div>

            {originalChanges.length > 0 && <div className="change-summary"><h3>Changes made by DevOps</h3>{originalChanges.map((change) => <div key={change.key}><strong>{change.key.replace(/_/g, " ")}</strong><span>{change.requested}</span><span>→</span><span>{change.approved}</span></div>)}</div>}

            {selected.provisioning && Object.keys(selected.provisioning).length > 0 && <div className="provision-grid"><h3>Provisioning Status</h3>{Object.entries(selected.provisioning).map(([name, step]) => <div className="provision-step" key={name}><strong>{name}</strong><span className={`status ${statusClass(step.status)}`}>{step.status}</span><small>{step.message}</small>{step.url && <a href={step.url} target="_blank" rel="noreferrer">Open resource</a>}</div>)}</div>}

            {selected.timeline && selected.timeline.length > 0 && <div className="timeline"><h3>Timeline</h3>{selected.timeline.map((event, index) => <div key={`${event.at}-${index}`}><strong>{event.action}</strong><span>{event.actor} · {new Date(event.at).toLocaleString()}</span><small>{event.detail}</small></div>)}</div>}

            {role === "devops" && ["Pending Approval", "Pending Action", "Partially Completed"].includes(selected.status) && <div className="modal-actions"><button disabled={busy} className="secondary-button" onClick={saveChanges}>Save Changes</button><button disabled={busy} className="danger-button" onClick={reject}>Reject</button><button disabled={busy} className="primary-button" onClick={approve}>{busy ? "Processing..." : "Approve & Provision"}</button></div>}
          </article>
        </div>
      )}
    </section>
  );
}
