import { FormEvent, useEffect, useMemo, useState } from "react";
import { Database, ExternalLink, Eye, Plus, RefreshCw, Save, Server, Settings } from "lucide-react";
import PremiumDeploymentModal from "../components/PremiumDeploymentModal";
import {
  applyDatasourceOperation,
  createDatasourceEnvironment,
  getDatasourceEnvironments,
  getDatasourceOperations,
  previewDatasources,
  updateDatasourceEnvironment,
  type WebLogicEnvironmentInput,
} from "../services/api";
import type { DatasourceOperation, WebLogicEnvironment } from "../types";

const PAT_SESSION_KEY = "devops-portal-azure-pat";

type Notice = { variant: "success" | "warning" | "error" | "info"; message: string };

const emptyEnvironment: WebLogicEnvironmentInput = {
  application: "OBP",
  environment: "txcsit",
  instance_name: "app1",
  base_path: "",
  domain_name: "",
  admin_host: "",
  admin_port: 5001,
  ssh_port: 22,
  wlst_path: "",
  agent_pool: "TitanNonProd-Release",
  default_db_host: "",
  default_db_port: 1531,
  default_ons_nodes: "",
  weblogic_username: "",
  weblogic_password: "",
  ssh_username: "",
  ssh_password: "",
  is_production: false,
  is_active: true,
};

function readPat() {
  try { return sessionStorage.getItem(PAT_SESSION_KEY) || ""; }
  catch { return ""; }
}

function statusClass(status?: string) {
  const value = String(status || "").toLowerCase();
  if (value.includes("complete") || value.includes("previewed") || value.includes("created") || value === "ready") return "success";
  if (value.includes("fail") || value.includes("invalid") || value.includes("already")) return "danger";
  if (value.includes("running") || value.includes("queued")) return "warning";
  return "neutral";
}

function formatDate(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function DatasourcesPage({ token, isAdmin }: { token: string; isAdmin: boolean }) {
  const [environments, setEnvironments] = useState<WebLogicEnvironment[]>([]);
  const [operations, setOperations] = useState<DatasourceOperation[]>([]);
  const [environmentId, setEnvironmentId] = useState<number>(0);
  const [referenceEntity, setReferenceEntity] = useState("");
  const [targetEntity, setTargetEntity] = useState("");
  const [datasourceType, setDatasourceType] = useState<"standalone" | "gridlink">("standalone");
  const [dbHost, setDbHost] = useState("");
  const [dbPort, setDbPort] = useState(1531);
  const [serviceId, setServiceId] = useState("");
  const [passwordPattern, setPasswordPattern] = useState("");
  const [onsNodes, setOnsNodes] = useState("");
  const [pat, setPat] = useState(readPat);
  const [patEditable, setPatEditable] = useState(false);
  const [selectedOperation, setSelectedOperation] = useState<DatasourceOperation | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmApply, setConfirmApply] = useState(false);

  const [showConfig, setShowConfig] = useState(false);
  const [editingEnvironmentId, setEditingEnvironmentId] = useState<number | null>(null);
  const [environmentForm, setEnvironmentForm] = useState<WebLogicEnvironmentInput>({ ...emptyEnvironment });

  const selectedEnvironment = environments.find((item) => item.id === environmentId) || null;
  const existingTargetProfile = useMemo(
    () => selectedEnvironment?.entities.find((item) => item.entity_code.toUpperCase() === targetEntity.trim().toUpperCase()) || null,
    [selectedEnvironment, targetEntity],
  );

  async function load() {
    try {
      const [envRows, operationRows] = await Promise.all([
        getDatasourceEnvironments(token),
        getDatasourceOperations(token),
      ]);
      setEnvironments(envRows);
      setOperations(operationRows);
      setEnvironmentId((current) => {
        if (current && envRows.some((item) => item.id === current)) return current;
        return envRows.find((item) => item.is_active)?.id || envRows[0]?.id || 0;
      });
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to load datasource configuration" });
    }
  }

  useEffect(() => { void load(); }, [token]);

  useEffect(() => {
    try {
      if (pat) sessionStorage.setItem(PAT_SESSION_KEY, pat);
      else sessionStorage.removeItem(PAT_SESSION_KEY);
    } catch { /* session storage unavailable */ }
  }, [pat]);

  useEffect(() => {
    if (!selectedEnvironment) return;
    setDbHost(selectedEnvironment.default_db_host);
    setDbPort(selectedEnvironment.default_db_port);
    setOnsNodes(selectedEnvironment.default_ons_nodes || "");
    setTargetEntity("");
    setReferenceEntity("");
    setServiceId("");
    setPasswordPattern("");
    setSelectedOperation(null);
  }, [environmentId]);

  useEffect(() => {
    if (!existingTargetProfile) return;
    setDbHost(existingTargetProfile.db_host);
    setDbPort(existingTargetProfile.db_port);
    setServiceId(existingTargetProfile.service_id);
    setOnsNodes(existingTargetProfile.ons_nodes || "");
    setPasswordPattern("");
  }, [existingTargetProfile?.id]);

  async function preview(event: FormEvent) {
    event.preventDefault();
    if (!selectedEnvironment) return;
    if (!passwordPattern && !existingTargetProfile?.password_pattern_configured) {
      setNotice({ variant: "error", message: "Password pattern is required the first time an entity is configured." });
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      const result = await previewDatasources({
        environment_instance_id: selectedEnvironment.id,
        reference_entity: referenceEntity,
        target_entity: targetEntity,
        datasource_type: datasourceType,
        db_host: dbHost,
        db_port: Number(dbPort),
        service_id: serviceId,
        password_pattern: passwordPattern || undefined,
        ons_nodes: datasourceType === "gridlink" ? onsNodes : "",
        azure_devops_pat: pat,
      }, token);
      setPasswordPattern("");
      setSelectedOperation(result);
      setNotice({
        variant: "success",
        message: `Preview ${result.request_id} completed from the live WebLogic configuration. Review the datasource plan before applying.`,
      });
      await load();
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Datasource preview failed" });
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!selectedOperation) return;
    setConfirmApply(false);
    setBusy(true);
    setNotice(null);
    try {
      const result = await applyDatasourceOperation(selectedOperation.id, pat, token);
      setSelectedOperation(result);
      setNotice({ variant: "success", message: `${result.request_id} completed. WebLogic datasource changes were applied through WLST.` });
      await load();
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to apply datasource changes" });
    } finally {
      setBusy(false);
    }
  }

  function beginEnvironment(environment?: WebLogicEnvironment) {
    setShowConfig(true);
    setNotice(null);
    if (!environment) {
      setEditingEnvironmentId(null);
      setEnvironmentForm({ ...emptyEnvironment });
      return;
    }
    setEditingEnvironmentId(environment.id);
    setEnvironmentForm({
      application: environment.application,
      environment: environment.environment,
      instance_name: environment.instance_name,
      base_path: environment.base_path,
      domain_name: environment.domain_name,
      admin_host: environment.admin_host,
      admin_port: environment.admin_port,
      ssh_port: environment.ssh_port,
      wlst_path: environment.wlst_path,
      agent_pool: environment.agent_pool,
      default_db_host: environment.default_db_host,
      default_db_port: environment.default_db_port,
      default_ons_nodes: environment.default_ons_nodes,
      weblogic_username: environment.weblogic_username,
      weblogic_password: "",
      ssh_username: environment.ssh_username,
      ssh_password: "",
      is_production: environment.is_production,
      is_active: environment.is_active,
    });
  }

  async function saveEnvironment(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const payload = {
        ...environmentForm,
        weblogic_password: environmentForm.weblogic_password || undefined,
        ssh_password: environmentForm.ssh_password || undefined,
        admin_port: Number(environmentForm.admin_port),
        ssh_port: Number(environmentForm.ssh_port),
        default_db_port: Number(environmentForm.default_db_port),
      };
      if (editingEnvironmentId) {
        await updateDatasourceEnvironment(editingEnvironmentId, payload, token);
      } else {
        await createDatasourceEnvironment(payload, token);
      }
      setEnvironmentForm((current) => ({ ...current, weblogic_password: "", ssh_password: "" }));
      setNotice({ variant: "success", message: editingEnvironmentId ? "WebLogic environment updated." : "WebLogic environment created." });
      setShowConfig(false);
      await load();
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to save WebLogic environment" });
    } finally {
      setBusy(false);
    }
  }

  const plan = selectedOperation?.preview;
  const canPreview = Boolean(
    selectedEnvironment &&
    referenceEntity.trim() &&
    targetEntity.trim() &&
    serviceId.trim() &&
    dbHost.trim() &&
    pat.trim() &&
    !busy
  );

  return <div className="datasources-page">
    <section className="datasource-hero">
      <div>
        <span className="eyebrow">WEBLOGIC AUTOMATION</span>
        <h1>Datasources</h1>
        <p>Clone live WebLogic datasource configuration from a reference entity, preview the exact changes, then apply them through WLST.</p>
      </div>
      <Database size={46} />
    </section>

    {notice && <div className={`datasource-notice ${notice.variant}`}>{notice.message}</div>}

    {isAdmin && <section className="datasource-config-panel">
      <div className="datasource-section-title">
        <div><Settings size={21}/><div><h2>Application environments</h2><p>Database-backed replacement for per-application vars.yaml files.</p></div></div>
        <button className="secondary-button" type="button" onClick={() => beginEnvironment()}><Plus size={15}/>Add environment</button>
      </div>
      <div className="datasource-environment-list">
        {environments.map((item) => <button type="button" key={item.id} onClick={() => beginEnvironment(item)}>
          <span><strong>{item.application}</strong><small>{item.environment} · {item.instance_name}</small></span>
          <span><strong>{item.domain_name}</strong><small>{item.admin_host}:{item.admin_port}</small></span>
          <span className={item.weblogic_password_configured && item.ssh_password_configured ? "credential-ok" : "credential-missing"}>
            {item.weblogic_password_configured && item.ssh_password_configured ? "Credentials configured" : "Credentials incomplete"}
          </span>
        </button>)}
        {environments.length === 0 && <div className="datasource-empty">No WebLogic environments configured yet.</div>}
      </div>
    </section>}

    {isAdmin && showConfig && <form className="datasource-config-form form-card" onSubmit={saveEnvironment}>
      <div className="full-width datasource-section-title">
        <div><Server size={21}/><div><h2>{editingEnvironmentId ? "Edit WebLogic environment" : "Add WebLogic environment"}</h2><p>Each application/environment/instance keeps its own connection, DB defaults, credentials and execution agent.</p></div></div>
      </div>

      <label>Application<input required value={environmentForm.application} onChange={(e) => setEnvironmentForm({ ...environmentForm, application: e.target.value.toUpperCase() })} placeholder="OBP"/></label>
      <label>Environment<input required value={environmentForm.environment} onChange={(e) => setEnvironmentForm({ ...environmentForm, environment: e.target.value.toLowerCase() })} placeholder="txcsit"/></label>
      <label>Instance<input required value={environmentForm.instance_name} onChange={(e) => setEnvironmentForm({ ...environmentForm, instance_name: e.target.value })} placeholder="app1"/></label>
      <label>Domain<input required value={environmentForm.domain_name} onChange={(e) => setEnvironmentForm({ ...environmentForm, domain_name: e.target.value })} placeholder="TXOBPSIT"/></label>
      <label>Admin / SSH host<input required value={environmentForm.admin_host} onChange={(e) => setEnvironmentForm({ ...environmentForm, admin_host: e.target.value })}/></label>
      <label>WebLogic Admin port<input type="number" min={1} max={65535} required value={environmentForm.admin_port} onChange={(e) => setEnvironmentForm({ ...environmentForm, admin_port: Number(e.target.value) })}/></label>
      <label>SSH port<input type="number" min={1} max={65535} required value={environmentForm.ssh_port} onChange={(e) => setEnvironmentForm({ ...environmentForm, ssh_port: Number(e.target.value) })}/></label>
      <label>Base path<input value={environmentForm.base_path} onChange={(e) => setEnvironmentForm({ ...environmentForm, base_path: e.target.value })} placeholder="/obpay"/></label>
      <label className="full-width">WLST path<input required value={environmentForm.wlst_path} onChange={(e) => setEnvironmentForm({ ...environmentForm, wlst_path: e.target.value })} placeholder="/obpay/Oracle/Middleware/.../wlst.sh"/></label>
      <label>Azure agent pool<input required value={environmentForm.agent_pool} onChange={(e) => setEnvironmentForm({ ...environmentForm, agent_pool: e.target.value })}/></label>
      <label>Default DB host<input required value={environmentForm.default_db_host} onChange={(e) => setEnvironmentForm({ ...environmentForm, default_db_host: e.target.value })}/></label>
      <label>Default DB port<input type="number" min={1} max={65535} required value={environmentForm.default_db_port} onChange={(e) => setEnvironmentForm({ ...environmentForm, default_db_port: Number(e.target.value) })}/></label>
      <label>Default ONS nodes<input value={environmentForm.default_ons_nodes} onChange={(e) => setEnvironmentForm({ ...environmentForm, default_ons_nodes: e.target.value })} placeholder="host1:6200,host2:6200"/></label>

      <label>WebLogic username<input required value={environmentForm.weblogic_username} onChange={(e) => setEnvironmentForm({ ...environmentForm, weblogic_username: e.target.value })}/></label>
      <label>WebLogic password<input type="password" value={environmentForm.weblogic_password || ""} onChange={(e) => setEnvironmentForm({ ...environmentForm, weblogic_password: e.target.value })} autoComplete="new-password" data-lpignore="true" data-1p-ignore="true" placeholder={editingEnvironmentId ? "Leave blank to keep existing" : "Required before execution"}/></label>
      <label>SSH username<input required value={environmentForm.ssh_username} onChange={(e) => setEnvironmentForm({ ...environmentForm, ssh_username: e.target.value })}/></label>
      <label>SSH password<input type="password" value={environmentForm.ssh_password || ""} onChange={(e) => setEnvironmentForm({ ...environmentForm, ssh_password: e.target.value })} autoComplete="new-password" data-lpignore="true" data-1p-ignore="true" placeholder={editingEnvironmentId ? "Leave blank to keep existing" : "Required before execution"}/></label>

      <label className="datasource-checkbox"><input type="checkbox" checked={environmentForm.is_production} onChange={(e) => setEnvironmentForm({ ...environmentForm, is_production: e.target.checked })}/>Production environment</label>
      <label className="datasource-checkbox"><input type="checkbox" checked={environmentForm.is_active} onChange={(e) => setEnvironmentForm({ ...environmentForm, is_active: e.target.checked })}/>Active</label>

      <div className="full-width datasource-form-actions">
        <button className="primary-button" disabled={busy}><Save size={15}/>{busy ? "Saving..." : "Save environment"}</button>
        <button className="secondary-button" type="button" disabled={busy} onClick={() => setShowConfig(false)}>Cancel</button>
      </div>
    </form>}

    <section className="datasource-workspace">
      <div className="datasource-section-title">
        <div><Eye size={21}/><div><h2>Clone datasource entity</h2><p>Only entity-specific values are supplied here. Pool settings, driver, transaction protocol and targets are read live from the reference datasource.</p></div></div>
        <button className="secondary-button" type="button" onClick={() => void load()}><RefreshCw size={15}/>Refresh</button>
      </div>

      {environments.length === 0 ? <div className="datasource-empty">A DevOps administrator must configure at least one WebLogic application environment first.</div> :
      <form className="form-card datasource-operation-form" onSubmit={preview}>
        <label className="full-width">Application / Environment
          <select value={environmentId} onChange={(e) => setEnvironmentId(Number(e.target.value))}>
            {environments.map((item) => <option key={item.id} value={item.id}>
              {item.application} · {item.environment.toUpperCase()} · {item.instance_name}{item.is_active ? "" : " (inactive)"}
            </option>)}
          </select>
        </label>

        {selectedEnvironment && <div className="full-width datasource-environment-summary">
          <span><small>Domain</small><strong>{selectedEnvironment.domain_name}</strong></span>
          <span><small>AdminServer</small><strong>{selectedEnvironment.admin_host}:{selectedEnvironment.admin_port}</strong></span>
          <span><small>Agent pool</small><strong>{selectedEnvironment.agent_pool}</strong></span>
          <span><small>Credentials</small><strong>{selectedEnvironment.weblogic_password_configured && selectedEnvironment.ssh_password_configured ? "Configured" : "Incomplete"}</strong></span>
        </div>}

        <label>Reference entity<input required value={referenceEntity} onChange={(e) => setReferenceEntity(e.target.value.toUpperCase())} placeholder="QA"/></label>
        <label>Target entity<input required value={targetEntity} onChange={(e) => setTargetEntity(e.target.value.toUpperCase())} placeholder="IN" list="configured-datasource-entities"/></label>
        <datalist id="configured-datasource-entities">{selectedEnvironment?.entities.map((item) => <option key={item.id} value={item.entity_code}/>)}</datalist>

        <label>Datasource type<select value={datasourceType} onChange={(e) => setDatasourceType(e.target.value as "standalone" | "gridlink")}><option value="standalone">Standalone</option><option value="gridlink">GridLink</option></select></label>
        <label>Service ID<input required value={serviceId} onChange={(e) => setServiceId(e.target.value)} placeholder="TXPMINS"/></label>
        <label>Database host<input required value={dbHost} onChange={(e) => setDbHost(e.target.value)}/></label>
        <label>Database port<input type="number" min={1} max={65535} required value={dbPort} onChange={(e) => setDbPort(Number(e.target.value))}/></label>

        <label className="full-width">Password pattern
          <input type="password" value={passwordPattern} onChange={(e) => setPasswordPattern(e.target.value)} autoComplete="new-password" data-lpignore="true" data-1p-ignore="true" placeholder={existingTargetProfile?.password_pattern_configured ? "Leave blank to reuse the encrypted saved pattern" : "{username}TXCORE"}/>
          <small>{existingTargetProfile?.password_pattern_configured ? "An encrypted pattern is already stored for this target entity." : "Use {username} where the derived target schema username should be inserted. The pattern is encrypted before it is stored."}</small>
        </label>

        {datasourceType === "gridlink" && <label className="full-width">ONS nodes<input required value={onsNodes} onChange={(e) => setOnsNodes(e.target.value)} placeholder="host1:6200,host2:6200"/></label>}

        <label className="full-width">Azure DevOps PAT
          <input type="password" name="datasource-azure-devops-pat" value={pat} onChange={(e) => setPat(e.target.value)} onFocus={() => setPatEditable(true)} readOnly={!patEditable} autoComplete="new-password" data-lpignore="true" data-1p-ignore="true" spellCheck={false} placeholder="PAT is kept only for this browser session"/>
        </label>

        <div className="full-width datasource-form-actions">
          <button className="primary-button" disabled={!canPreview}><Eye size={15}/>{busy ? "Running preview..." : "Preview from WebLogic"}</button>
        </div>
      </form>}
    </section>

    {plan && selectedOperation && <section className="datasource-plan">
      <div className="datasource-section-title">
        <div><Database size={21}/><div><h2>Preview · {selectedOperation.request_id}</h2><p>{plan.application} / {plan.environment.toUpperCase()} · {plan.reference_entity} → {plan.target_entity}</p></div></div>
        <span className={`status ${statusClass(selectedOperation.status)}`}>{selectedOperation.status}</span>
      </div>

      <div className="table-card">
        <table>
          <thead><tr><th>Reference</th><th>New datasource</th><th>JNDI</th><th>Schema</th><th>Database</th><th>Targets</th><th>Type</th><th>Status</th></tr></thead>
          <tbody>{plan.datasources.map((item) => <tr key={item.target_name}>
            <td><strong>{item.source_name}</strong><small>{item.source_jndis?.join(", ") || "—"}</small></td>
            <td><strong>{item.target_name}</strong></td>
            <td>{item.target_jndis?.join(", ") || "—"}</td>
            <td>{item.source_user} → <strong>{item.target_user}</strong></td>
            <td><small>{item.target_url}</small></td>
            <td>{item.source_targets?.join(", ") || "—"}<small>→ {item.target_targets?.join(", ") || "—"}</small></td>
            <td>{item.driver_name?.includes("XA") ? "XA" : "Generic"}</td>
            <td><span className={`status ${statusClass(item.status)}`}>{item.status}</span>{item.missing_targets?.length ? <small>Missing: {item.missing_targets.join(", ")}</small> : null}</td>
          </tr>)}</tbody>
        </table>
      </div>

      <div className="datasource-plan-actions">
        {selectedOperation.azure_run_url && <a href={selectedOperation.azure_run_url} target="_blank" rel="noreferrer"><ExternalLink size={15}/>Open preview run</a>}
        {selectedOperation.status === "Previewed" && <button className="primary-button" disabled={busy || plan.datasources.some((item) => item.status !== "Ready")} onClick={() => setConfirmApply(true)}>Create Datasources</button>}
      </div>
    </section>}

    <section className="datasource-history">
      <div className="datasource-section-title"><div><Database size={21}/><div><h2>Recent datasource operations</h2><p>Preview and apply audit history. Secrets are never returned in this view.</p></div></div></div>
      <div className="table-card">
        <table>
          <thead><tr><th>Request</th><th>Reference → Target</th><th>Type</th><th>Requested by</th><th>Status</th><th>Updated</th><th>Run</th></tr></thead>
          <tbody>{operations.map((item) => <tr key={item.id} onClick={() => item.preview && setSelectedOperation(item)} className={item.preview ? "datasource-history-clickable" : ""}>
            <td><strong>{item.request_id}</strong></td>
            <td>{item.reference_entity} → <strong>{item.target_entity}</strong></td>
            <td>{item.datasource_type}</td>
            <td>{item.requested_by}</td>
            <td><span className={`status ${statusClass(item.status)}`}>{item.status}</span></td>
            <td>{formatDate(item.updated_at)}</td>
            <td>{item.azure_run_url ? <a href={item.azure_run_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}><ExternalLink size={15}/></a> : "—"}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>

    <PremiumDeploymentModal
      open={confirmApply}
      variant="warning"
      eyebrow="WEBLOGIC CHANGE"
      title="Create these datasources?"
      message="This action will connect to the configured WebLogic AdminServer and apply the previewed datasource plan through WLST."
      details={[
        { label: "Request", value: selectedOperation?.request_id || "" },
        { label: "Environment", value: selectedEnvironment ? `${selectedEnvironment.application} / ${selectedEnvironment.environment.toUpperCase()}` : "" },
        { label: "Entity", value: selectedOperation ? `${selectedOperation.reference_entity} → ${selectedOperation.target_entity}` : "" },
        { label: "Datasources", value: String(selectedOperation?.preview?.datasources?.length || 0) },
      ]}
      primaryLabel="Create Datasources"
      secondaryLabel="Keep preview only"
      busy={busy}
      onPrimary={() => void apply()}
      onSecondary={() => setConfirmApply(false)}
    />
  </div>;
}
