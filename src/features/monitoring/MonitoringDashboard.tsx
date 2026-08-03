import {
  Activity,
  AlertTriangle,
  Boxes,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  CloudCog,
  FolderKanban,
  GitBranch,
  Network,
  RefreshCw,
  Rocket,
  ServerCog,
  Workflow,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getMonitoringSummary } from "./api";
import type { MonitoringSection, MonitoringSummary } from "./types";

interface Props { token: string; }

const sectionLabels: Record<MonitoringSection, string> = {
  overview: "Monitoring Home",
  kubernetes: "Kubernetes",
  project: "Project Monitoring",
  pipelines: "Pipelines",
  deployments: "Deployments",
  provisioning: "Provisioning",
  exceptions: "Exceptions",
};

function statusClass(status: string): string {
  const value = status.toLowerCase();
  if (["healthy", "completed", "closed", "already exists"].includes(value)) return "healthy";
  if (["warning", "pending approval", "approved"].includes(value)) return "warning";
  if (["stale", "missing", "failed", "rejected", "partially completed"].includes(value)) return "danger-status";
  return "progress";
}

function formatTime(value?: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString();
}

function Metric({ label, value, detail }: { label: string; value: number; detail: string }) {
  return <div className="monitoring-detail-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}

export default function MonitoringDashboard({ token }: Props) {
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeSection, setActiveSection] = useState<MonitoringSection>("overview");
  const [selectedCluster, setSelectedCluster] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const next = await getMonitoringSummary(token);
      setSummary(next);
      setSelectedCluster((current) => current || next.clusters[0]?.name || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load monitoring data");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { void load(); }, [load]);

  const healthyClusters = useMemo(() => summary?.clusters.filter((cluster) => cluster.status === "Healthy").length ?? 0, [summary]);
  const activeCluster = useMemo(() => summary?.clusters.find((cluster) => cluster.name === selectedCluster) ?? summary?.clusters[0], [selectedCluster, summary]);

  if (loading && !summary) return <div className="monitoring-state-card"><div className="loading-spinner"/><strong>Loading operations control center...</strong></div>;

  return <section className="monitoring-dashboard">
    <div className="section-heading monitoring-heading">
      <div>
        <span className="eyebrow">OPERATIONS CONTROL CENTER</span>
        <h2>{sectionLabels[activeSection]}</h2>
        <p>{activeSection === "overview" ? "Select an operational area to open detailed monitoring." : "Live operational data from the DevOps Portal and synchronized Kubernetes inventory."}</p>
      </div>
      <div className="monitoring-heading-actions">
        {activeSection !== "overview" && <button className="secondary-button monitoring-refresh" onClick={() => setActiveSection("overview")}><ChevronLeft size={17}/>Monitoring home</button>}
        <button className="secondary-button monitoring-refresh" disabled={loading} onClick={() => void load()}><RefreshCw size={17} className={loading ? "spin" : ""}/>{loading ? "Refreshing..." : "Refresh"}</button>
      </div>
    </div>

    {error && <div className="form-error">{error}</div>}

    {summary && <>
      <div className="monitoring-hero">
        <div><span className="eyebrow">CURRENT PLATFORM STATE</span><h3>{healthyClusters} of {summary.clusters.length} Kubernetes targets reporting healthy inventory</h3><p>Telemetry refreshed {formatTime(summary.generated_at)}</p></div>
        <div className="monitoring-hero-pulse"><span/><div className="monitoring-hero-icon"><ServerCog size={34}/></div></div>
      </div>

      {activeSection === "overview" && <div className="monitoring-category-grid">
        <button className="monitoring-category-card kubernetes-card" onClick={() => setActiveSection("kubernetes")}><div className="monitoring-category-icon"><ServerCog/></div><span>KUBERNETES</span><h3>Cluster Overview</h3><p>Clusters, namespaces, services, ingresses and inventory freshness.</p><strong>{summary.clusters.length} targets</strong><ChevronRight/></button>
        <button className="monitoring-category-card project-card" onClick={() => setActiveSection("project")}><div className="monitoring-category-icon"><FolderKanban/></div><span>PROJECTS</span><h3>Project Monitoring</h3><p>Onboarding requests, project status, applications and delivery progress.</p><strong>{summary.provisioning_activity.length} recent projects</strong><ChevronRight/></button>
        <button className="monitoring-category-card pipeline-card" onClick={() => setActiveSection("pipelines")}><div className="monitoring-category-icon"><Workflow/></div><span>AZURE DEVOPS</span><h3>Pipeline Monitoring</h3><p>Running pipelines, build setup, release setup and failures.</p><strong>{summary.pipeline_metrics.running} running</strong><ChevronRight/></button>
        <button className="monitoring-category-card deployment-card" onClick={() => setActiveSection("deployments")}><div className="monitoring-category-icon"><Rocket/></div><span>DELIVERY</span><h3>Deployment Status</h3><p>Manual/direct and pipeline-based Kubernetes deployment activity.</p><strong>{summary.deployment_metrics.completed} completed</strong><ChevronRight/></button>
        <button className="monitoring-category-card provisioning-card" onClick={() => setActiveSection("provisioning")}><div className="monitoring-category-icon"><Activity/></div><span>PROVISIONING</span><h3>Provisioning Flow</h3><p>Approval, DevOps queue, running, completed and partial requests.</p><strong>{summary.provisioning_metrics.running} in progress</strong><ChevronRight/></button>
        <button className="monitoring-category-card exception-card" onClick={() => setActiveSection("exceptions")}><div className="monitoring-category-icon"><AlertTriangle/></div><span>ATTENTION</span><h3>Exceptions</h3><p>Failed, rejected and partially completed onboarding activity.</p><strong>{summary.recent_failures.length} recent issues</strong><ChevronRight/></button>
      </div>}

      {activeSection !== "overview" && <nav className="monitoring-section-tabs" aria-label="Monitoring sections">
        {(["kubernetes", "project", "pipelines", "deployments", "provisioning", "exceptions"] as MonitoringSection[]).map((section) => <button key={section} className={activeSection === section ? "active" : ""} onClick={() => setActiveSection(section)}>{sectionLabels[section]}</button>)}
      </nav>}

      {activeSection !== "overview" && <div className="monitoring-card-grid">{summary.cards.map((card) => <article key={card.key} className={`monitoring-metric-card tone-${card.tone}`}><span>{card.label}</span><strong>{card.value}</strong><small>{card.detail}</small></article>)}</div>}

      {activeSection === "kubernetes" && <div className="monitoring-layout">
        <article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">KUBERNETES CONTROL PLANE</span><h3>Cluster overview</h3></div><small>Inventory: {formatTime(summary.inventory_generated_at)}</small></div><div className="monitoring-cluster-list">{summary.clusters.map((cluster) => <button className={`monitoring-cluster-row ${selectedCluster === cluster.name ? "selected" : ""}`} key={cluster.name} onClick={() => setSelectedCluster(cluster.name)}><div className="monitoring-cluster-main"><div className={`monitoring-status-icon ${statusClass(cluster.status)}`}>{cluster.status === "Healthy" ? <CheckCircle2 size={18}/> : <AlertTriangle size={18}/>}</div><div><strong>{cluster.name}</strong><span>{cluster.mode}</span></div></div><div className="monitoring-cluster-counts"><div><strong>{cluster.namespaces}</strong><span>Namespaces</span></div><div><strong>{cluster.services}</strong><span>Services</span></div><div><strong>{cluster.ingresses}</strong><span>Ingresses</span></div></div><div className="monitoring-sync"><span className={`status ${statusClass(cluster.status)}`}>{cluster.status}</span><small><Clock3 size={13}/>{cluster.age_minutes == null ? "No sync data" : `${cluster.age_minutes} min ago`}</small></div></button>)}</div></article>
        <article className="monitoring-panel monitoring-focus-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">SELECTED TARGET</span><h3>{activeCluster?.name || "No cluster"}</h3></div><CloudCog size={22}/></div>{activeCluster && <><div className="monitoring-mini-metrics"><Metric label="Namespaces" value={activeCluster.namespaces} detail="Available"/><Metric label="Services" value={activeCluster.services} detail="Discovered"/><Metric label="Ingresses" value={activeCluster.ingresses} detail="Routing resources"/></div><div className="monitoring-namespace-list">{activeCluster.namespace_details.map((namespace) => <div key={namespace.name}><div><Boxes size={16}/><strong>{namespace.name}</strong></div><span>{namespace.services} services</span><span>{namespace.ingresses} ingresses</span></div>)}</div></>}</article>
      </div>}

      {activeSection === "project" && <div className="monitoring-layout"><article className="monitoring-panel monitoring-feature-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">PROJECT DELIVERY</span><h3>Project monitoring</h3><p>Onboarding projects grouped by their current workflow state.</p></div><FolderKanban size={23}/></div><div className="monitoring-detail-grid compact"><Metric label="Pending approval" value={summary.provisioning_metrics.pending_approval} detail="Application owner review"/><Metric label="Approved" value={summary.provisioning_metrics.approved} detail="Waiting for DevOps"/><Metric label="In progress" value={summary.provisioning_metrics.running} detail="Currently provisioning"/><Metric label="Completed" value={summary.provisioning_metrics.completed} detail="Delivered or closed"/><Metric label="Issues" value={summary.provisioning_metrics.failed_partial} detail="Failed or partial"/></div></article><article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">PROJECT FLOW</span><h3>Status distribution</h3></div><GitBranch size={22}/></div><div className="monitoring-status-list">{Object.entries(summary.request_statuses).map(([status, count]) => <div key={status}><span>{status}</span><strong>{count}</strong></div>)}</div></article></div>}

      {activeSection === "pipelines" && <article className="monitoring-panel monitoring-feature-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">AZURE DEVOPS</span><h3>Pipeline monitoring</h3><p>Pipeline counts currently reflect onboarding activity recorded by the portal.</p></div><Workflow size={24}/></div><div className="monitoring-detail-grid"><Metric label="Running currently" value={summary.pipeline_metrics.running} detail="Pipeline setup executing"/><Metric label="Builds completed" value={summary.pipeline_metrics.build_created} detail="Created or reused"/><Metric label="Release definitions" value={summary.pipeline_metrics.release_created} detail="Cloned successfully"/><Metric label="Build failures" value={summary.pipeline_metrics.build_failed} detail="Needs attention"/><Metric label="Release failures" value={summary.pipeline_metrics.release_failed} detail="Needs attention"/></div></article>}

      {activeSection === "deployments" && <article className="monitoring-panel monitoring-feature-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">DELIVERY STATUS</span><h3>Deployment monitoring</h3><p>Direct backend deployments and Azure Pipeline based remote deployments.</p></div><Rocket size={24}/></div><div className="monitoring-detail-grid"><Metric label="Deployments completed" value={summary.deployment_metrics.completed} detail="Service and ingress completed"/><Metric label="Manual / direct" value={summary.deployment_metrics.direct} detail="Backend Kubernetes client"/><Metric label="YAML / pipeline based" value={summary.deployment_metrics.pipeline_based} detail="Remote build agent"/><Metric label="Services completed" value={summary.deployment_metrics.services_completed} detail="Created or validated"/><Metric label="Ingress completed" value={summary.deployment_metrics.ingresses_completed} detail="Paths updated"/></div></article>}

      {activeSection === "provisioning" && <div className="monitoring-layout"><article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">ONBOARDING WORKFLOW</span><h3>Provisioning monitoring</h3></div><Activity size={23}/></div><div className="monitoring-detail-grid compact"><Metric label="Pending approval" value={summary.provisioning_metrics.pending_approval} detail="With application owners"/><Metric label="Approved" value={summary.provisioning_metrics.approved} detail="Waiting for DevOps"/><Metric label="Running" value={summary.provisioning_metrics.running} detail="In progress"/><Metric label="Completed" value={summary.provisioning_metrics.completed} detail="Completed or closed"/><Metric label="Failed / partial" value={summary.provisioning_metrics.failed_partial} detail="Follow-up required"/></div></article><article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">REQUEST FLOW</span><h3>Status distribution</h3></div><GitBranch size={22}/></div><div className="monitoring-status-list">{Object.entries(summary.request_statuses).map(([status, count]) => <div key={status}><span>{status}</span><strong>{count}</strong></div>)}</div></article></div>}

      {["project", "pipelines", "deployments", "provisioning"].includes(activeSection) && <article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">RECENT EXECUTION</span><h3>Provisioning and delivery activity</h3></div><Network size={22}/></div><div className="table-card monitoring-table"><table><thead><tr><th>Request</th><th>Repository</th><th>Cluster</th><th>Build</th><th>Release</th><th>Service</th><th>Ingress</th><th>Status</th></tr></thead><tbody>{summary.provisioning_activity.map((item) => <tr key={item.id}><td><strong>{item.id}</strong></td><td>{item.repository}</td><td>{item.target_cluster}</td><td><span className={`status ${statusClass(item.pipeline_status)}`}>{item.pipeline_status}</span></td><td><span className={`status ${statusClass(item.release_status)}`}>{item.release_status}</span></td><td><span className={`status ${statusClass(item.service_status)}`}>{item.service_status}</span></td><td><span className={`status ${statusClass(item.ingress_status)}`}>{item.ingress_status}</span></td><td><span className={`status ${statusClass(item.status)}`}>{item.status}</span></td></tr>)}</tbody></table></div></article>}

      {activeSection === "exceptions" && <article className="monitoring-panel"><div className="monitoring-panel-header"><div><span className="eyebrow">ATTENTION REQUIRED</span><h3>Recent failed, rejected or partial requests</h3></div><AlertTriangle size={22}/></div>{summary.recent_failures.length === 0 ? <div className="monitoring-empty"><CheckCircle2 size={22}/><span>No recent request exceptions.</span></div> : <div className="table-card monitoring-table"><table><thead><tr><th>Request</th><th>Repository</th><th>Application</th><th>Status</th><th>Updated</th><th>Detail</th></tr></thead><tbody>{summary.recent_failures.map((item) => <tr key={item.id}><td><strong>{item.id}</strong></td><td>{item.repository}</td><td>{item.application}</td><td><span className={`status ${statusClass(item.status)}`}>{item.status}</span></td><td>{formatTime(item.updated_at)}</td><td>{item.detail || "No additional detail"}</td></tr>)}</tbody></table></div>}</article>}
    </>}
  </section>;
}
