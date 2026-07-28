import { useEffect, useState } from "react";
import { getPipelineRequests } from "../services/api";
import type { PipelineRequest, Role } from "../types";

interface Props { token: string; role: Role; refreshKey: number; }

export default function RequestsPage({ token, role, refreshKey }: Props) {
  const [requests, setRequests] = useState<PipelineRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    getPipelineRequests(token).then(setRequests).catch(reason => setError(reason.message)).finally(() => setLoading(false));
  }, [token, refreshKey]);

  return <section><div className="section-heading"><div><span className="eyebrow">PIPELINE ONBOARDING</span><h2>{role === "devops" ? "All Pipeline Requests" : "My Pipeline Requests"}</h2><p>Track submitted repository, pipeline, ingress and service creation requests.</p></div></div>
    <div className="table-card">{loading ? <p>Loading requests...</p> : error ? <div className="form-error">{error}</div> : requests.length === 0 ? <p>No requests have been submitted yet.</p> : <table><thead><tr><th>Request ID</th><th>Application</th><th>Repository</th><th>Namespace</th><th>Service</th><th>Status</th><th>Requested By</th><th>Created</th></tr></thead><tbody>{requests.map(request => <tr key={request.id}><td><strong>{request.id}</strong></td><td>{request.application_name}</td><td>{request.repository_name}</td><td>{request.namespace}</td><td>{request.create_service ? `${request.service_name}:${request.service_port}` : "Not requested"}</td><td><span className="status pending">{request.status}</span></td><td>{request.requested_by}</td><td>{new Date(request.created_at).toLocaleString()}</td></tr>)}</tbody></table>}</div>
  </section>;
}
