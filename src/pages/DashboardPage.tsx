import { useEffect, useMemo, useState } from "react";
import { getPipelineRequests } from "../services/api";
import type { PipelineRequest, Role } from "../types";

interface Props {
  token: string;
  role: Role;
  refreshKey: number;
}

const statusClass = (status: string) => {
  const value = status.toLowerCase();
  if (value.includes("complete") || value.includes("closed")) return "healthy";
  if (value.includes("reject") || value.includes("fail")) return "danger-status";
  if (value.includes("provision") || value.includes("progress") || value.includes("partial")) return "progress";
  return "pending";
};

export default function DashboardPage({ token, role, refreshKey }: Props) {
  const [requests, setRequests] = useState<PipelineRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    getPipelineRequests(token)
      .then(setRequests)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load dashboard data"))
      .finally(() => setLoading(false));
  }, [token, refreshKey]);

  const stats = useMemo(() => {
    const pending = requests.filter((item) => ["Waiting for App Owner Approval", "Pending Approval"].includes(item.status)).length;
    const inProgress = requests.filter((item) => ["Provisioning", "Pending Action", "Partially Completed"].includes(item.status)).length;
    const completed = requests.filter((item) => ["Completed", "Closed"].includes(item.status)).length;
    return [
      [role === "devops" ? "Provisioning Queue" : "My Requests", requests.length],
      ["Pending Approval", pending],
      ["In Progress", inProgress],
      ["Completed", completed],
    ] as const;
  }, [requests, role]);

  const recent = requests.slice(0, 8);

  return <section>
    <div className="section-heading"><div><span className="eyebrow">OVERVIEW</span><h2>Dashboard</h2><p>Live request statistics and recent onboarding activity.</p></div></div>
    {error && <div className="form-error">{error}</div>}
    <div className="stats-grid">{stats.map(([label, value]) => <article className="stat-card" key={label}><strong>{loading ? "—" : value}</strong><span>{label}</span></article>)}</div>
    <article className="table-card">
      <h3>Recent activity</h3>
      {loading ? <p>Loading recent activity...</p> : recent.length === 0 ? <p>No pipeline requests have been submitted yet.</p> : <table>
        <thead><tr><th>Request</th><th>Repository</th><th>Application</th><th>Requested By</th><th>Status</th><th>Updated</th></tr></thead>
        <tbody>{recent.map((request) => <tr key={request.id}>
          <td><strong>{request.id}</strong></td>
          <td>{request.repository_name}</td>
          <td>{request.application_type}</td>
          <td>{request.requested_by}</td>
          <td><span className={`status ${statusClass(request.status)}`}>{request.status}</span></td>
          <td>{new Date(request.updated_at || request.created_at).toLocaleString()}</td>
        </tr>)}</tbody>
      </table>}
    </article>
  </section>;
}
