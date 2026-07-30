import { useEffect, useMemo, useState } from "react";
import { CalendarDays, RefreshCw } from "lucide-react";
import { getPipelineRequests } from "../services/api";
import type { PipelineRequest, Role } from "../types";

interface Props {
  token: string;
  role: Role;
  refreshKey: number;
}

const RANGE_OPTIONS = [7, 14, 30, 60, 90, 180, 365] as const;

const statusClass = (status: string) => {
  const value = status.toLowerCase();
  if (value.includes("complete") || value.includes("closed")) return "healthy";
  if (value.includes("reject") || value.includes("fail")) return "danger-status";
  if (value.includes("provision") || value.includes("progress") || value.includes("partial")) return "progress";
  return "pending";
};

const requestTimestamp = (request: PipelineRequest) => {
  const value = request.updated_at || request.created_at;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
};

export default function DashboardPage({ token, role, refreshKey }: Props) {
  const [requests, setRequests] = useState<PipelineRequest[]>([]);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    setError("");
    getPipelineRequests(token)
      .then(setRequests)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load dashboard data"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [token, refreshKey]);

  const filteredRequests = useMemo(() => {
    const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
    return requests
      .filter((request) => requestTimestamp(request) >= cutoff)
      .sort((left, right) => requestTimestamp(right) - requestTimestamp(left));
  }, [requests, days]);

  const stats = useMemo(() => {
    const provisioningQueue = filteredRequests.filter((item) =>
      ["Pending Approval", "Pending Action", "Partially Completed"].includes(item.status),
    ).length;
    const rejected = filteredRequests.filter((item) => item.status === "Rejected").length;
    const inProgress = filteredRequests.filter((item) => item.status === "Provisioning").length;
    const completed = filteredRequests.filter((item) => ["Completed", "Closed"].includes(item.status)).length;
    const waitingForOwner = filteredRequests.filter((item) => item.status === "Waiting for App Owner Approval").length;

    if (role === "devops") {
      return [
        ["Provisioning Queue", provisioningQueue, "Requests ready for DevOps action"],
        ["Rejected", rejected, "Rejected during the selected period"],
        ["In Progress", inProgress, "Provisioning currently running"],
        ["Completed", completed, "Completed or closed requests"],
      ] as const;
    }

    return [
      ["My Requests", filteredRequests.length, "Requests submitted in this period"],
      ["Waiting for App Owner", waitingForOwner, "Awaiting application-owner decision"],
      ["Rejected", rejected, "Rejected requests"],
      ["Completed", completed, "Completed or closed requests"],
    ] as const;
  }, [filteredRequests, role]);

  const recent = filteredRequests.slice(0, 12);

  return (
    <section>
      <div className="section-heading dashboard-heading">
        <div>
          <span className="eyebrow">OVERVIEW</span>
          <h2>Dashboard</h2>
          <p>Live onboarding statistics and recent activity for the selected reporting period.</p>
        </div>
        <div className="dashboard-toolbar">
          <label className="date-range-control">
            <CalendarDays size={18} />
            <span>Period</span>
            <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
              {RANGE_OPTIONS.map((value) => (
                <option key={value} value={value}>Last {value} days</option>
              ))}
            </select>
          </label>
          <button className="dashboard-refresh-button" type="button" onClick={load} disabled={loading}>
            <RefreshCw size={17} className={loading ? "spin-icon" : ""} />
            Refresh
          </button>
        </div>
      </div>

      <div className="dashboard-period-banner">
        <div>
          <span>Reporting window</span>
          <strong>Last {days} days through today</strong>
        </div>
        <div>
          <span>Matching requests</span>
          <strong>{loading ? "—" : filteredRequests.length}</strong>
        </div>
      </div>

      {error && <div className="form-error">{error}</div>}

      <div className="stats-grid dashboard-stats-grid">
        {stats.map(([label, value, description]) => (
          <article className="stat-card dashboard-stat-card" key={label}>
            <div className="stat-card-glow" />
            <strong>{loading ? "—" : value}</strong>
            <span>{label}</span>
            <small>{description}</small>
          </article>
        ))}
      </div>

      <article className="table-card dashboard-activity-card">
        <div className="dashboard-table-heading">
          <div>
            <span className="eyebrow">ACTIVITY</span>
            <h3>Recent activity</h3>
          </div>
          <span className="dashboard-result-count">{recent.length} shown</span>
        </div>

        {loading ? (
          <p>Loading recent activity...</p>
        ) : recent.length === 0 ? (
          <div className="dashboard-empty-state">
            <CalendarDays size={28} />
            <strong>No requests found</strong>
            <span>No onboarding activity was recorded during the last {days} days.</span>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Request</th>
                <th>Repository</th>
                <th>Application</th>
                <th>Requested By</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((request) => (
                <tr key={request.id}>
                  <td><strong>{request.id}</strong></td>
                  <td>{request.repository_name}</td>
                  <td>{request.application_type}</td>
                  <td>{request.requested_by}</td>
                  <td><span className={`status ${statusClass(request.status)}`}>{request.status}</span></td>
                  <td>{new Date(request.updated_at || request.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </article>
    </section>
  );
}
