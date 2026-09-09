import GtbDeliveryPlanner from "../components/GtbDeliveryPlanner";
import { FormEvent, useEffect, useState } from "react";
import { Bot, Play, RefreshCw } from "lucide-react";
import { getAgentRuns, getAgentScopes, runAgent, type AgentRun, type AgentScope } from "../services/api";
import "./gtb-agent.css";

export default function GtbAgentPage({ token }: { token: string }) {
  const [scopes, setScopes] = useState<AgentScope[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [scopeId, setScopeId] = useState("");
  const [objective, setObjective] = useState<"health" | "connectivity" | "readiness">("health");
  const [active, setActive] = useState<AgentRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([getAgentScopes(token), getAgentRuns(token)]).then(([configured, history]) => {
      if (cancelled) return;
      setScopes(configured); setScopeId(configured[0]?.id ?? ""); setRuns(history); setActive(history[0] ?? null);
    }).catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : "Unable to load the agent"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token]);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const report = await runAgent({ scope_id: scopeId, objective }, token);
      setActive(report); setRuns(previous => [report, ...previous].slice(0, 25));
    } catch (e) { setError(e instanceof Error ? e.message : "Investigation failed"); }
    finally { setBusy(false); }
  }

  return <section className="gtb-agent">
    <header className="gtb-heading"><Bot size={30} /><div><h1>GTB Operations Agent</h1><p>Investigate application infrastructure and review the evidence before taking action.</p></div></header>
    <GtbDeliveryPlanner token={token}/>
    {error && <div className="gtb-error" role="alert">{error}</div>}
    <form className="gtb-panel gtb-controls" onSubmit={submit}>
      <label>Application scope<select value={scopeId} onChange={e => setScopeId(e.target.value)} disabled={loading || busy || !scopes.length} required>
        {!scopes.length && <option value="">{loading ? "Loading scopes…" : "No application scopes configured"}</option>}
        {scopes.map(scope => <option key={scope.id} value={scope.id}>{scope.application} · {scope.environment} · {scope.namespace} · {scope.cluster}</option>)}
      </select></label>
      <label>Investigation<select value={objective} onChange={e => setObjective(e.target.value as typeof objective)} disabled={busy}>
        <option value="health">Workload health</option><option value="connectivity">Service connectivity</option><option value="readiness">Infrastructure readiness</option>
      </select></label>
      <button className="primary-button" disabled={busy || loading || !scopeId}><Play size={16} />{busy ? "Investigating…" : "Run investigation"}</button>
    </form>
    {!loading && !scopes.length && <div className="gtb-panel"><h2>Configure your application scopes</h2><p>Ask the portal administrator to map each GTB application environment to its cluster and namespace in GTB_AGENT_SCOPES. Only configured, allowed namespaces can be investigated.</p></div>}
    <p className="gtb-note" role="status">{busy ? "Collecting pod and deployment status, then checking related resources. This can take up to a minute." : "Rule-based diagnostics · Read-only Kubernetes tools · Changes require the existing deployment workflow"}</p>
    <div className="gtb-workspace">
      <aside className="gtb-panel"><h2>Your recent investigations</h2>{loading ? <p>Loading history…</p> : !runs.length ? <p>No investigations yet. Select an application scope to begin.</p> : runs.map(run => <button className={`gtb-history ${active?.id === run.id ? "selected" : ""}`} key={run.id} onClick={() => setActive(run)}>
        <strong>{run.scope.application} · {run.scope.environment}</strong><span>{run.objective} · {run.assessment.replace(/_/g, " ")}</span><time dateTime={run.created_at}>{new Date(run.created_at).toLocaleString()}</time>
      </button>)}</aside>
      <div className="gtb-report" aria-live="polite">{active ? <>
        <article className="gtb-panel"><div className="gtb-result-title"><h2>{active.assessment.replace(/_/g, " ")}</h2><span className="role-badge">{active.status}</span></div>
          <p>{active.scope.application} / {active.scope.cluster} / {active.scope.namespace}</p><p>Observed {new Date(active.created_at).toLocaleString()} · {active.objective}</p>
          {active.findings.length === 0 && <p>{active.assessment === "unknown" ? "Evidence is unavailable or incomplete. Application health cannot be determined." : "No issues detected by the completed checks. Review the limitations below."}</p>}
          {active.findings.map((finding, index) => <div className={`gtb-finding ${finding.severity}`} key={`${finding.code}-${index}`}><strong>{finding.severity.toUpperCase()} · {finding.resource}</strong><p>{finding.detail}</p><p><b>Next step:</b> {finding.recommendation}</p><small>Evidence: {finding.evidence_tool} · {finding.code}</small></div>)}
        </article>
        <article className="gtb-panel"><h2>Evidence and tool trace</h2>{active.trace.map(step => <details key={step.tool}><summary>{step.tool} · {step.status} · {step.evidence.length} resources</summary><pre>{JSON.stringify(step.evidence, null, 2)}</pre></details>)}</article>
        <article className="gtb-panel"><h2>Limits of this investigation</h2><ul>{active.limitations.map((limit, i) => <li key={i}>{limit}</li>)}</ul><p>Review proposed changes in <a href="/devops-portal/deployment-management">Deployment Management</a>. This report does not approve or execute them.</p></article>
      </> : <article className="gtb-panel gtb-empty"><RefreshCw size={28} /><h2>Start with a live investigation</h2><p>The agent checks pods and deployments, then inspects storage or service endpoints when the objective or evidence calls for it.</p></article>}</div>
    </div>
  </section>;
}
