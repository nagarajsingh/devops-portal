import { AlertTriangle, CheckCircle2, Clock3, RefreshCw, ServerCog } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getMonitoringSummary } from "./api";
import type { MonitoringSummary } from "./types";

interface Props {
  token: string;
}

function statusClass(status: string): string {
  const value = status.toLowerCase();
  if (value === "healthy") return "healthy";
  if (value === "warning") return "warning";
  if (value === "stale" || value === "missing") return "danger-status";
  return "progress";
}

function formatTime(value?: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString();
}

export default function MonitoringDashboard({ token }: Props) {
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setSummary(await getMonitoringSummary(token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load monitoring data");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const healthyClusters = useMemo(
    () => summary?.clusters.filter((cluster) => cluster.status === "Healthy").length ?? 0,
    [summary],
  );

  if (loading && !summary) {
    return <div className="monitoring-state-card"><div className="loading-spinner"/><strong>Loading live monitoring data...</strong></div>;
  }

  return <section className="monitoring-dashboard">
    <div className="section-heading monitoring-heading">
      <div>
        <span className="eyebrow">OPERATIONS CONTROL CENTER</span>
        <h2>Monitoring</h2>
        <p>Cluster inventory, request health and recent provisioning exceptions from live portal data.</p>
      </div>
      <button className="secondary-button monitoring-refresh" disabled={loading} onClick={() => void load()}>
        <RefreshCw size={17} className={loading ? "spin" : ""}/>
        {loading ? "Refreshing..." : "Refresh"}
      </button>
    </div>

    {error && <div className="form-error">{error}</div>}

    {summary && <>
      <div className="monitoring-hero">
        <div>
          <span className="eyebrow">CURRENT PLATFORM STATE</span>
          <h3>{healthyClusters} of {summary.clusters.length} clusters reporting healthy inventory</h3>
          <p>Last dashboard refresh: {formatTime(summary.generated_at)}</p>
        </div>
        <div className="monitoring-hero-icon"><ServerCog size={34}/></div>
      </div>

      <div className="monitoring-card-grid">
        {summary.cards.map((card) => <article key={card.label} className={`monitoring-metric-card tone-${card.tone}`}>
          <span>{card.label}</span>
          <strong>{card.value}</strong>
        </article>)}
      </div>

      <div className="monitoring-layout">
        <article className="monitoring-panel monitoring-clusters-panel">
          <div className="monitoring-panel-header">
            <div><span className="eyebrow">CLUSTER INVENTORY</span><h3>Environment status</h3></div>
            <small>Inventory generated: {formatTime(summary.inventory_generated_at)}</small>
          </div>
          <div className="monitoring-cluster-list">
            {summary.clusters.map((cluster) => <div className="monitoring-cluster-row" key={cluster.name}>
              <div className="monitoring-cluster-main">
                <div className={`monitoring-status-icon ${statusClass(cluster.status)}`}>
                  {cluster.status === "Healthy" ? <CheckCircle2 size={18}/> : <AlertTriangle size={18}/>} 
                </div>
                <div><strong>{cluster.name}</strong><span>{cluster.mode}</span></div>
              </div>
              <div className="monitoring-cluster-counts">
                <div><strong>{cluster.namespaces}</strong><span>Namespaces</span></div>
                <div><strong>{cluster.services}</strong><span>Services</span></div>
                <div><strong>{cluster.ingresses}</strong><span>Ingresses</span></div>
              </div>
              <div className="monitoring-sync">
                <span className={`status ${statusClass(cluster.status)}`}>{cluster.status}</span>
                <small><Clock3 size={13}/>{cluster.age_minutes == null ? "No sync data" : `${cluster.age_minutes} min ago`}</small>
              </div>
            </div>)}
          </div>
        </article>

        <article className="monitoring-panel">
          <div className="monitoring-panel-header"><div><span className="eyebrow">REQUEST FLOW</span><h3>Status distribution</h3></div></div>
          <div className="monitoring-status-list">
            {Object.entries(summary.request_statuses).length === 0 ? <p>No request data is available.</p> : Object.entries(summary.request_statuses).map(([status, count]) => <div key={status}><span>{status}</span><strong>{count}</strong></div>)}
          </div>
        </article>
      </div>

      <article className="monitoring-panel">
        <div className="monitoring-panel-header"><div><span className="eyebrow">ATTENTION REQUIRED</span><h3>Recent failed, rejected or partial requests</h3></div></div>
        {summary.recent_failures.length === 0 ? <div className="monitoring-empty"><CheckCircle2 size={22}/><span>No recent request exceptions.</span></div> : <div className="table-card monitoring-table"><table><thead><tr><th>Request</th><th>Repository</th><th>Application</th><th>Status</th><th>Updated</th><th>Detail</th></tr></thead><tbody>{summary.recent_failures.map((item) => <tr key={item.id}><td><strong>{item.id}</strong></td><td>{item.repository}</td><td>{item.application}</td><td><span className={`status ${statusClass(item.status)}`}>{item.status}</span></td><td>{formatTime(item.updated_at)}</td><td>{item.detail || "No additional detail"}</td></tr>)}</tbody></table></div>}
      </article>
    </>}
  </section>;
}
