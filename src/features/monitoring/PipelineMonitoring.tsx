import { ExternalLink, Workflow } from "lucide-react";
import type { LivePipelineMetrics, PipelineRun } from "./types";

function statusClass(value: string): string {
  const status = value.toLowerCase();
  if (["succeeded", "completed", "partiallysucceeded"].includes(status)) return "healthy";
  if (["failed", "canceled", "rejected"].includes(status)) return "danger-status";
  if (["queued", "notstarted", "postponed", "pending", "scheduled"].includes(status)) return "warning";
  return "progress";
}

function formatDate(value?: string): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString();
}

function RunTable({ title, rows }: { title: string; rows: PipelineRun[] }) {
  return <article className="monitoring-panel">
    <div className="monitoring-panel-header"><div><span className="eyebrow">LIVE DETAILS</span><h3>{title}</h3></div><Workflow size={22}/></div>
    {rows.length === 0 ? <div className="monitoring-empty">No records found for the selected period.</div> : <div className="table-card monitoring-table"><table>
      <thead><tr><th>Pipeline</th><th>Run / Environment</th><th>Type</th><th>Status</th><th>Result</th><th>Requested by</th><th>Started</th><th>Link</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={`${title}-${row.id}`}>
        <td><strong>{row.name}</strong></td>
        <td>{row.build_number || row.environment || row.release_name || "-"}</td>
        <td>{row.pipeline_type || (row.environment ? "Classic release" : "-")}</td>
        <td><span className={`status ${statusClass(row.status)}`}>{row.status}</span></td>
        <td><span className={`status ${statusClass(row.result || row.status)}`}>{row.result || "-"}</span></td>
        <td>{row.requested_by || "-"}</td>
        <td>{formatDate(row.start_time || row.started_on || row.queue_time)}</td>
        <td>{row.url ? <a href={row.url} target="_blank" rel="noreferrer" className="monitoring-link" aria-label={`Open ${row.name} in Azure DevOps`}><ExternalLink size={15}/></a> : "-"}</td>
      </tr>)}</tbody>
    </table></div>}
  </article>;
}

export default function PipelineMonitoring({ data }: { data?: LivePipelineMetrics }) {
  if (!data) return <div className="monitoring-state-card">Live Azure DevOps data is unavailable.</div>;
  return <div className="monitoring-detail-stack">
    <article className="monitoring-panel monitoring-feature-panel">
      <div className="monitoring-panel-header"><div><span className="eyebrow">TITAN PROJECT</span><h3>Build pipeline runs</h3><p>Period: {data.days === 1 ? "Today" : `Last ${data.days} days`}</p></div><Workflow size={24}/></div>
      <div className="monitoring-detail-grid">
        <div className="monitoring-detail-metric"><span>Running</span><strong>{data.running}</strong><small>Currently executing</small></div>
        <div className="monitoring-detail-metric"><span>In queue</span><strong>{data.queued}</strong><small>Waiting to start</small></div>
        <div className="monitoring-detail-metric"><span>Completed</span><strong>{data.builds_completed}</strong><small>{data.builds_succeeded} succeeded</small></div>
        <div className="monitoring-detail-metric"><span>Failed</span><strong>{data.builds_failed}</strong><small>Failed or cancelled</small></div>
        <div className="monitoring-detail-metric"><span>Definitions</span><strong>{data.definitions}</strong><small>Total build definitions</small></div>
      </div>
    </article>

    <div className="monitoring-layout">
      <article className="monitoring-panel monitoring-feature-panel">
        <div className="monitoring-panel-header"><div><span className="eyebrow">YAML DEPLOYMENTS</span><h3>Deploy-named pipelines</h3><p>Definitions containing “deploy”, such as new-cmncore-deploy-pipeline.</p></div></div>
        <div className="monitoring-detail-grid compact">
          <div className="monitoring-detail-metric"><span>Queued</span><strong>{data.yaml_deployments.queued}</strong><small>Waiting to start</small></div>
          <div className="monitoring-detail-metric"><span>Running</span><strong>{data.yaml_deployments.running}</strong><small>In progress</small></div>
          <div className="monitoring-detail-metric"><span>Completed</span><strong>{data.yaml_deployments.completed}</strong><small>Completed deployments</small></div>
          <div className="monitoring-detail-metric"><span>Failed</span><strong>{data.yaml_deployments.failed}</strong><small>Failed or cancelled</small></div>
          <div className="monitoring-detail-metric"><span>Definitions</span><strong>{data.yaml_deployments.definitions}</strong><small>Deploy-named definitions</small></div>
        </div>
      </article>

      <article className="monitoring-panel monitoring-feature-panel">
        <div className="monitoring-panel-header"><div><span className="eyebrow">CLASSIC RELEASES</span><h3>Classic deployment pipelines</h3></div></div>
        <div className="monitoring-detail-grid compact">
          <div className="monitoring-detail-metric"><span>Pending</span><strong>{data.classic.pending}</strong><small>Queued or scheduled</small></div>
          <div className="monitoring-detail-metric"><span>Running</span><strong>{data.classic.running}</strong><small>In progress</small></div>
          <div className="monitoring-detail-metric"><span>Completed</span><strong>{data.classic.completed}</strong><small>Succeeded</small></div>
          <div className="monitoring-detail-metric"><span>Failed</span><strong>{data.classic.failed}</strong><small>Failed, rejected or cancelled</small></div>
          <div className="monitoring-detail-metric"><span>Definitions</span><strong>{data.classic.definitions}</strong><small>Classic release definitions</small></div>
        </div>
      </article>
    </div>

    <article className="monitoring-panel monitoring-feature-panel">
      <div className="monitoring-panel-header"><div><span className="eyebrow">YAML BUILDS</span><h3>Non-deployment YAML pipelines</h3><p>YAML definitions without “deploy” in their pipeline name.</p></div></div>
      <div className="monitoring-detail-grid">
        <div className="monitoring-detail-metric"><span>Queued</span><strong>{data.yaml.queued}</strong><small>Waiting to start</small></div>
        <div className="monitoring-detail-metric"><span>Running</span><strong>{data.yaml.running}</strong><small>In progress</small></div>
        <div className="monitoring-detail-metric"><span>Completed</span><strong>{data.yaml.completed}</strong><small>Completed YAML builds</small></div>
        <div className="monitoring-detail-metric"><span>Failed</span><strong>{data.yaml.failed}</strong><small>Failed or cancelled</small></div>
        <div className="monitoring-detail-metric"><span>Definitions</span><strong>{data.yaml.definitions}</strong><small>Non-deployment YAML definitions</small></div>
      </div>
    </article>

    <RunTable title="Currently running builds" rows={data.running_runs}/>
    <RunTable title="Queued builds" rows={data.queued_runs}/>
    <RunTable title="YAML deployment pipeline runs" rows={data.yaml_deployments.runs}/>
    <RunTable title="Classic release deployments" rows={data.classic.deployments}/>
    <RunTable title="YAML build pipeline runs" rows={data.yaml.runs}/>
    <RunTable title="Recent completed builds" rows={data.completed_runs}/>
  </div>;
}
