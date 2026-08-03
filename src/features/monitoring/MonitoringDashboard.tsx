import { Activity, AlertTriangle, Boxes, CheckCircle2, ChevronLeft, ChevronRight, Clock3, CloudCog, FolderKanban, GitBranch, RefreshCw, Rocket, ServerCog, Workflow } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getMonitoringSummary } from "./api";
import PipelineMonitoring from "./PipelineMonitoring";
import type { MonitoringSection, MonitoringSummary } from "./types";

interface Props { token: string; }

const labels: Record<MonitoringSection, string> = {
  overview: "Monitoring Home", kubernetes: "Kubernetes", project: "Project Monitoring", pipelines: "Pipelines",
  deployments: "Deployments", provisioning: "Provisioning", exceptions: "Exceptions",
};

function statusClass(value: string): string {
  const status = value.toLowerCase();
  if (["healthy", "completed", "closed", "already exists", "succeeded"].includes(status)) return "healthy";
  if (["warning", "pending approval", "approved", "queued", "pending"].includes(status)) return "warning";
  if (["stale", "missing", "failed", "rejected", "partially completed", "canceled"].includes(status)) return "danger-status";
  return "progress";
}

function Metric({ label, value, detail }: { label: string; value: number | string; detail: string }) {
  return <div className="monitoring-detail-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}

export default function MonitoringDashboard({ token }: Props) {
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeSection, setActiveSection] = useState<MonitoringSection>("overview");
  const [selectedCluster, setSelectedCluster] = useState("");
  const [days, setDays] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const next = await getMonitoringSummary(token, days);
      setSummary(next);
      setSelectedCluster((current) => current || next.clusters[0]?.name || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load monitoring data");
    } finally {
      setLoading(false);
    }
  }, [token, days]);

  useEffect(() => { void load(); }, [load]);

  const healthyClusters = useMemo(() => summary?.clusters.filter((item) => item.status === "Healthy").length ?? 0, [summary]);
  const activeCluster = useMemo(() => summary?.clusters.find((item) => item.name === selectedCluster) ?? summary?.clusters[0], [selectedCluster, summary]);

  if (loading && !summary) return <div className="monitoring-state-card"><div className="loading-spinner"/><strong>Loading operations control center...</strong></div>;

  return <section className="monitoring-dashboard">
    <div className="section-heading monitoring-heading">
      <div><span className="eyebrow">OPERATIONS CONTROL CENTER</span><h2>{labels[activeSection]}</h2><p>{activeSection === "overview" ? "Select an operational area to open detailed monitoring." : "Live operational data from Kubernetes, Azure DevOps and the portal workflow."}</p></div>
      <div className="monitoring-heading-actions">
        {activeSection === "pipelines" && <label className="monitoring-range">Period<select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value={1}>Today</option><option value={3}>Last 3 days</option><option value={7}>Last 7 days</option><option value={14}>Last 14 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select></label>}
        {activeSection !== "overview" && <button className="secondary-button monitoring-refresh" onClick={() => setActiveSection("overview")}><ChevronLeft size={17}/>Monitoring home</button>}
        <button className="secondary-button monitoring-refresh" disabled={loading} onClick={() => void load()}><RefreshCw size={17} className={loading ? "spin" : ""}/>{loading ? "Refreshing..." : "Refresh"}</button>
      </div>
    </div>

    {error && <div className="form-error">{error}</div>}
    {summary && <>
      <div className="monitoring-hero"><div><span className="eyebrow">CURRENT PLATFORM STATE</span><h3>{healthyClusters} of {summary.clusters.length} Kubernetes targets reporting healthy</h3><p>Telemetry refreshed {new Date(summary.generated_at).toLocaleString()}</p></div><div className="monitoring-hero-icon"><ServerCog size={34}/></div></div>

      {activeSection === "overview" && <div className="monitoring-category-grid">
        <button className="monitoring-category-card kubernetes-card" onClick={() => setActiveSection("kubernetes")}><div className="monitoring-category-icon"><ServerCog/></div><span>KUBERNETES</span><h3>Cluster Overview</h3><p>Namespaces, workloads, networking and persistent volumes.</p><strong>{summary.clusters.length} targets</strong><ChevronRight/></button>
        <button className="monitoring-category-card project-card" onClick={() => setActiveSection("project")}><div className="monitoring-category-icon"><FolderKanban/></div><span>PROJECTS</span><h3>Project Monitoring</h3><p>Portal onboarding requests and project delivery progress.</p><strong>{summary.provisioning_activity.length} recent projects</strong><ChevronRight/></button>
        <button className="monitoring-category-card pipeline-card" onClick={() => setActiveSection("pipelines")}><div className="monitoring-category-icon"><Workflow/></div><span>AZURE DEVOPS</span><h3>Pipeline Monitoring</h3><p>Build runs, classic releases and YAML delivery pipelines.</p><strong>{summary.live_pipeline_metrics?.running ?? summary.pipeline_metrics.running} running</strong><ChevronRight/></button>
        <button className="monitoring-category-card deployment-card" onClick={() => setActiveSection("deployments")}><div className="monitoring-category-icon"><Rocket/></div><span>DELIVERY</span><h3>Deployment Status</h3><p>Portal-managed direct and remote deployments.</p><strong>{summary.deployment_metrics.completed} completed</strong><ChevronRight/></button>
        <button className="monitoring-category-card provisioning-card" onClick={() => setActiveSection("provisioning")}><div className="monitoring-category-icon"><Activity/></div><span>PROVISIONING</span><h3>Provisioning Flow</h3><p>Approvals, running requests and completion state.</p><strong>{summary.provisioning_metrics.running} in progress</strong><ChevronRight/></button>
        <button className="monitoring-category-card exception-card" onClick={() => setActiveSection("exceptions")}><div className="monitoring-category-icon"><AlertTriangle/></div><span>ATTENTION</span><h3>Exceptions</h3><p>Failed, rejected and partially completed requests.</p><strong>{summary.recent_failures.length} recent issues</strong><ChevronRight/></button>
      </div>}

      {activeSection !== "overview" && <nav className="monitoring-section-tabs">{(["kubernetes", "project", "pipelines", "deployments", "provisioning", "exceptions"] as MonitoringSection[]).map((item) => <button key={item} className={activeSection === item ? "active" : ""} onClick={() => setActiveSection(item)}>{labels[item]}</button>)}</nav>}

      {activeSection === "kubernetes" && <>
        <div className="monitoring-layout">
          <article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">KUBERNETES CONTROL PLANE</span><h3>Cluster overview</h3></div></div><div className="monitoring-cluster-list">{summary.clusters.map((cluster) => <button className={`monitoring-cluster-row ${selectedCluster === cluster.name ? "selected" : ""}`} key={cluster.name} onClick={() => setSelectedCluster(cluster.name)}><div className="monitoring-cluster-main"><div className={`monitoring-status-icon ${statusClass(cluster.status)}`}>{cluster.status === "Healthy" ? <CheckCircle2 size={18}/> : <AlertTriangle size={18}/>}</div><div><strong>{cluster.name}</strong><span>{cluster.mode}</span></div></div><div className="monitoring-cluster-counts"><div><strong>{cluster.namespaces}</strong><span>Namespaces</span></div><div><strong>{cluster.services}</strong><span>Services</span></div><div><strong>{cluster.ingresses}</strong><span>Ingresses</span></div></div><div className="monitoring-sync"><span className={`status ${statusClass(cluster.status)}`}>{cluster.status}</span><small><Clock3 size={13}/>{cluster.age_minutes == null ? "No sync data" : `${cluster.age_minutes} min ago`}</small></div></button>)}</div></article>
          <article className="monitoring-panel monitoring-focus-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">SELECTED TARGET</span><h3>{activeCluster?.name || "No cluster"}</h3></div><CloudCog size={22}/></div>{activeCluster && <><div className="monitoring-mini-metrics"><Metric label="Namespaces" value={activeCluster.namespaces} detail="Visible to service account"/><Metric label="Deployments" value={activeCluster.deployments ?? 0} detail={`${activeCluster.deployments_unhealthy ?? 0} unhealthy`}/><Metric label="Services" value={activeCluster.services} detail="Discovered"/><Metric label="Ingresses" value={activeCluster.ingresses} detail="Routing resources"/></div><div className="monitoring-namespace-list">{activeCluster.namespace_details.map((namespace) => <div key={namespace.name}><div><Boxes size={16}/><strong>{namespace.name}</strong></div><span>{namespace.deployments ?? 0} deployments</span><span>{namespace.services} services</span><span>{namespace.ingresses} ingresses</span></div>)}</div></>}</article>
        </div>
        {activeCluster?.storage && <article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">PERSISTENT STORAGE</span><h3>Persistent volume allocation</h3><p>Allocated and available values represent Kubernetes PV capacity versus bound claims, not filesystem consumption.</p></div></div><div className="monitoring-detail-grid compact"><Metric label="Total capacity" value={`${activeCluster.storage.capacity_gib} GiB`} detail="PV capacity"/><Metric label="Allocated" value={`${activeCluster.storage.allocated_gib} GiB`} detail="Capacity bound to claims"/><Metric label="Available" value={`${activeCluster.storage.available_gib} GiB`} detail="Unbound capacity"/></div><div className="table-card monitoring-table"><table><thead><tr><th>PV</th><th>Status</th><th>Capacity</th><th>Allocated</th><th>Available</th><th>Claim</th><th>Storage class</th><th>Access</th></tr></thead><tbody>{(activeCluster.persistent_volumes || []).map((pv) => <tr key={pv.name}><td><strong>{pv.name}</strong></td><td><span className={`status ${statusClass(pv.status)}`}>{pv.status}</span></td><td>{pv.capacity_gib} GiB</td><td>{pv.allocated_gib} GiB</td><td>{pv.available_gib} GiB</td><td>{pv.claim || "-"}</td><td>{pv.storage_class || "-"}</td><td>{pv.access_modes.join(", ")}</td></tr>)}</tbody></table></div></article>}
      </>}

      {activeSection === "pipelines" && <PipelineMonitoring data={summary.live_pipeline_metrics}/>} 

      {activeSection === "project" && <div className="monitoring-layout"><article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">PROJECT DELIVERY</span><h3>Project monitoring</h3></div><FolderKanban size={23}/></div><div className="monitoring-detail-grid compact"><Metric label="Pending approval" value={summary.provisioning_metrics.pending_approval} detail="Application owner review"/><Metric label="Approved" value={summary.provisioning_metrics.approved} detail="Waiting for DevOps"/><Metric label="In progress" value={summary.provisioning_metrics.running} detail="Provisioning"/><Metric label="Completed" value={summary.provisioning_metrics.completed} detail="Delivered or closed"/><Metric label="Issues" value={summary.provisioning_metrics.failed_partial} detail="Failed or partial"/></div></article><article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">PROJECT FLOW</span><h3>Status distribution</h3></div><GitBranch size={22}/></div><div className="monitoring-status-list">{Object.entries(summary.request_statuses).map(([status, count]) => <div key={status}><span>{status}</span><strong>{count}</strong></div>)}</div></article></div>}

      {activeSection === "deployments" && <article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">PORTAL DELIVERY</span><h3>Portal-managed deployment status</h3></div><Rocket size={24}/></div><div className="monitoring-detail-grid"><Metric label="Completed" value={summary.deployment_metrics.completed} detail="Service and ingress completed"/><Metric label="Direct" value={summary.deployment_metrics.direct} detail="Backend Kubernetes client"/><Metric label="Pipeline based" value={summary.deployment_metrics.pipeline_based} detail="Remote build agent"/><Metric label="Services" value={summary.deployment_metrics.services_completed} detail="Created or validated"/><Metric label="Ingresses" value={summary.deployment_metrics.ingresses_completed} detail="Paths updated"/></div></article>}

      {activeSection === "provisioning" && <article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">ONBOARDING</span><h3>Provisioning workflow</h3></div><Activity size={23}/></div><div className="monitoring-detail-grid compact"><Metric label="Pending approval" value={summary.provisioning_metrics.pending_approval} detail="Application owners"/><Metric label="Approved" value={summary.provisioning_metrics.approved} detail="Waiting for DevOps"/><Metric label="Running" value={summary.provisioning_metrics.running} detail="In progress"/><Metric label="Completed" value={summary.provisioning_metrics.completed} detail="Completed or closed"/><Metric label="Failed / partial" value={summary.provisioning_metrics.failed_partial} detail="Follow-up required"/></div></article>}

      {activeSection === "exceptions" && <article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">ATTENTION REQUIRED</span><h3>Recent exceptions</h3></div><AlertTriangle size={22}/></div>{summary.recent_failures.length === 0 ? <div className="monitoring-empty">No recent request exceptions.</div> : <div className="table-card monitoring-table"><table><thead><tr><th>Request</th><th>Repository</th><th>Application</th><th>Status</th><th>Detail</th></tr></thead><tbody>{summary.recent_failures.map((item) => <tr key={item.id}><td><strong>{item.id}</strong></td><td>{item.repository}</td><td>{item.application}</td><td><span className={`status ${statusClass(item.status)}`}>{item.status}</span></td><td>{item.detail || "-"}</td></tr>)}</tbody></table></div>}</article>}
    </>}
  </section>;
}
