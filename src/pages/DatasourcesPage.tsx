import { FormEvent, useEffect, useMemo, useState } from "react";
import { Database, ExternalLink, Eye, Plus, RefreshCw, Save, Server, Settings } from "lucide-react";
import PremiumDeploymentModal from "../components/PremiumDeploymentModal";
import {
  applyDatasourceOperation,
  createDatasourceEnvironment,
  getDatasourceApplications,
  getDatasourceEnvironments,
  getDatasourceOperations,
  previewDatasources,
  updateDatasourceEnvironment,
  type WebLogicEnvironmentInput,
} from "../services/api";
import type { DatasourceApplication, DatasourceOperation, WebLogicEnvironment } from "../types";

const PAT_SESSION_KEY = "devops-portal-azure-pat";

type Notice = { variant: "success" | "warning" | "error" | "info"; message: string };

type EnvironmentPreset = {
  inventory_hostname: string;
  admin_host: string;
};

const TXCSIT_HOST_PRESETS: Record<string, EnvironmentPreset> = {
  OBP: { inventory_hostname: "obp_txcsit_app1", admin_host: "172.24.178.164" },
  OBTF: { inventory_hostname: "obtf_txcsit_app1", admin_host: "172.24.178.168" },
  OBTFPM: { inventory_hostname: "obtfpm_txcsit_app1", admin_host: "172.24.178.167" },
  OBLM: { inventory_hostname: "oblm_txcsit_app1", admin_host: "172.24.178.165" },
  OBLMIC: { inventory_hostname: "oblmic_txcsit_app1", admin_host: "172.24.178.165" },
  OBVAM: { inventory_hostname: "obvam_txcsit_app1", admin_host: "172.24.178.166" },
  OBVAMIC: { inventory_hostname: "obvamic_txcsit_app1", admin_host: "172.24.178.166" },
  PLATO: { inventory_hostname: "plato_txcsit_app1", admin_host: "172.24.178.169" },
  CMNCORE: { inventory_hostname: "cmncore_txcsit_app1", admin_host: "172.24.178.169" },
  MOCORE: { inventory_hostname: "moc_txcsit_app1", admin_host: "172.24.178.167" },
};

const TXCSIT_DB_HOST = "gtbtxcoreobpmdbsit.uat.mashreqdev.com";
const TXCSIT_DB_PORT = 1531;
const TXCSIT_ONS_NODES = "gtbtxcoreobpmdbsit.uat.mashreqdev.com:6200,gtbtxcoreobpmdbsit.uat.mashreqdev.com:6200";

function wlstForBase(basePath: string) {
  const base = basePath.trim().replace(/\/$/, "");
  return base ? `${base}/Oracle/Middleware/Oracle_Home/oracle_common/common/bin/wlst.sh` : "";
}

function derivedArtifactPaths(environment: string, root = "/azure_artifact") {
  const cleanRoot = root.trim().replace(/\/$/, "") || "/azure_artifact";
  const env = environment.trim().toLowerCase();
  const common = env ? `${cleanRoot}/${env}` : cleanRoot;
  return {
    common,
    channel: `${common}/channel`,
    ear: `${common}/consulting/deploy/`,
  };
}

const emptyEnvironment: WebLogicEnvironmentInput = {
  application: "OBP",
  environment: "txcsit",
  instance_name: "app1",
  inventory_hostname: "",
  base_path: "",
  domain_name: "",
  admin_host: "",
  admin_port: 5001,
  ssh_port: 22,
  wlst_path: "",
  artifacts_location: "/azure_artifact",
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
  const [applications, setApplications] = useState<DatasourceApplication[]>([]);
  const [environments, setEnvironments] = useState<WebLogicEnvironment[]>([]);
  const [operations, setOperations] = useState<DatasourceOperation[]>([]);

  const [selectedApplication, setSelectedApplication] = useState("");
  const [environmentId, setEnvironmentId] = useState<number>(0);
  const [referenceEntity, setReferenceEntity] = useState("");
  const [targetEntity, setTargetEntity] = useState("");
  const [datasourceType, setDatasourceType] = useState<"standalone" | "gridlink">("standalone");
  const [dbHost, setDbHost] = useState("");
  const [dbPort, setDbPort] = useState(1531);
  const [serviceId, setServiceId] = useState("");
  const [schemaUsername, setSchemaUsername] = useState("");
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

  const applicationEnvironments = useMemo(
    () => environments.filter((item) => item.application === selectedApplication && item.is_active),
    [environments, selectedApplication],
  );
  const selectedEnvironment = environments.find((item) => item.id === environmentId) || null;
  const existingTargetProfile = useMemo(
    () => selectedEnvironment?.entities.find((item) => item.entity_code.toUpperCase() === targetEntity.trim().toUpperCase()) || null,
    [selectedEnvironment, targetEntity],
  );

  async function load() {
    try {
      const [appRows, envRows, operationRows] = await Promise.all([
        getDatasourceApplications(token),
        getDatasourceEnvironments(token),
        getDatasourceOperations(token),
      ]);
      setApplications(appRows);
      setEnvironments(envRows);
      setOperations(operationRows);

      setSelectedApplication((current) => {
        if (current && appRows.some((item) => item.code === current)) return current;
        return appRows[0]?.code || "";
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
    if (!selectedApplication) return;
    const options = environments.filter((item) => item.application === selectedApplication && item.is_active);
    setEnvironmentId((current) => options.some((item) => item.id === current) ? current : options[0]?.id || 0);
  }, [selectedApplication, environments]);

  useEffect(() => {
    if (!selectedEnvironment) {
      setDbHost("");
      setDbPort(1531);
      setOnsNodes("");
      return;
    }
    setDbHost(selectedEnvironment.default_db_host || "");
    setDbPort(selectedEnvironment.default_db_port || 1531);
    setOnsNodes(selectedEnvironment.default_ons_nodes || "");
    setTargetEntity("");
    setReferenceEntity("");
    setServiceId("");
    setSchemaUsername("");
    setPasswordPattern("");
    setSelectedOperation(null);
  }, [environmentId]);

  useEffect(() => {
    if (!existingTargetProfile) return;
    setDbHost(existingTargetProfile.db_host);
    setDbPort(existingTargetProfile.db_port);
    setServiceId(existingTargetProfile.service_id);
    setSchemaUsername(existingTargetProfile.schema_username);
    setOnsNodes(existingTargetProfile.ons_nodes || "");
    setPasswordPattern("");
  }, [existingTargetProfile?.id]);

  function beginEnvironment(environment?: WebLogicEnvironment) {
    setShowConfig(true);
    setNotice(null);
    if (!environment) {
      setEditingEnvironmentId(null);
      const app = applications[0]?.code || "OBP";
      setEnvironmentForm({ ...emptyEnvironment, application: app });
      return;
    }

    setEditingEnvironmentId(environment.id);
    setEnvironmentForm({
      application: environment.application,
      environment: environment.environment,
      instance_name: environment.instance_name,
      inventory_hostname: environment.inventory_hostname,
      base_path: environment.base_path,
      domain_name: environment.domain_name,
      admin_host: environment.admin_host,
      admin_port: environment.admin_port,
      ssh_port: environment.ssh_port,
      wlst_path: environment.wlst_path,
      artifacts_location: environment.artifacts_location || "/azure_artifact",
      agent_pool: environment.agent_pool,
      default_db_host: environment.default_db_host || "",
      default_db_port: environment.default_db_port || 1531,
      default_ons_nodes: environment.default_ons_nodes || "",
      weblogic_username: environment.weblogic_username,
      weblogic_password: "",
      ssh_username: environment.ssh_username,
      ssh_password: "",
      is_production: environment.is_production,
      is_active: environment.is_active,
    });
  }

  function applyTxcsitPreset(application = environmentForm.application) {
    const preset = TXCSIT_HOST_PRESETS[application];
    if (!preset) {
      setNotice({ variant: "warning", message: `No TXCSIT host preset is defined for ${application}.` });
      return;
    }
    setEnvironmentForm((current) => ({
      ...current,
      application,
      environment: "txcsit",
      instance_name: "app1",
      inventory_hostname: preset.inventory_hostname,
      admin_host: preset.admin_host,
      admin_port: current.admin_port || 5001,
      artifacts_location: "/azure_artifact",
      default_db_host: TXCSIT_DB_HOST,
      default_db_port: TXCSIT_DB_PORT,
      default_ons_nodes: TXCSIT_ONS_NODES,
    }));
    setNotice({ variant: "info", message: `Loaded TXCSIT host and database defaults for ${application}. Add/verify BASE, domain, users and passwords before saving.` });
  }

  function changeBasePath(value: string) {
    setEnvironmentForm((current) => {
      const oldSuggested = wlstForBase(current.base_path);
      const shouldReplace = !current.wlst_path || current.wlst_path === oldSuggested;
      return {
        ...current,
        base_path: value,
        wlst_path: shouldReplace ? wlstForBase(value) : current.wlst_path,
      };
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
        default_db_port: Number(environmentForm.default_db_port || 1531),
      };

      const saved = editingEnvironmentId
        ? await updateDatasourceEnvironment(editingEnvironmentId, payload, token)
        : await createDatasourceEnvironment(payload, token);

      setEnvironmentForm((current) => ({ ...current, weblogic_password: "", ssh_password: "" }));
      setNotice({
        variant: "success",
        message: editingEnvironmentId
          ? `${saved.application} / ${saved.environment.toUpperCase()} server configuration updated in the database.`
          : `${saved.application} / ${saved.environment.toUpperCase()} server configuration saved to the database.`,
      });
      setShowConfig(false);
      await load();
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to save WebLogic environment" });
    } finally {
      setBusy(false);
    }
  }

  async function preview(event: FormEvent) {
    event.preventDefault();
    if (!selectedEnvironment) return;
    if (!passwordPattern && !existingTargetProfile?.password_pattern_configured) {
      setNotice({ variant: "error", message: "Schema password pattern is required the first time this entity is configured." });
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
        schema_username: schemaUsername,
        password_pattern: passwordPattern || undefined,
        ons_nodes: datasourceType === "gridlink" ? onsNodes : "",
        azure_devops_pat: pat,
      }, token);
      setPasswordPattern("");
      setSelectedOperation(result);
      setNotice({
        variant: "success",
        message: `Preview ${result.request_id} completed from live WebLogic. Review the proposed datasource names and targets before creation.`,
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
      const count = result.preview?.summary?.created_count ?? result.preview?.datasources.filter((item) => item.status === "Created").length ?? 0;
      setNotice({ variant: "success", message: `${result.request_id} completed successfully. ${count} datasource(s) created.` });
      await load();
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to create datasource changes" });
    } finally {
      setBusy(false);
    }
  }

  const artifactPreview = derivedArtifactPaths(environmentForm.environment, environmentForm.artifacts_location);
  const plan = selectedOperation?.preview;
  const createdItems = plan?.datasources.filter((item) => item.status === "Created") || [];
  const canPreview = Boolean(
    selectedEnvironment &&
    referenceEntity.trim() &&
    targetEntity.trim() &&
    serviceId.trim() &&
    schemaUsername.trim() &&
    dbHost.trim() &&
    pat.trim() &&
    !busy
  );

  return <div className="datasources-page">
    <section className="datasource-hero">
      <div>
        <span className="eyebrow">WEBLOGIC AUTOMATION</span>
        <h1>Datasources</h1>
        <p>Maintain WebLogic server details in the portal database, clone datasource configuration from a live reference entity and create the new entity through WLST.</p>
      </div>
      <Database size={46} />
    </section>

    {notice && <div className={`datasource-notice ${notice.variant}`}>{notice.message}</div>}

    {isAdmin && <section className="datasource-config-panel">
      <div className="datasource-section-title">
        <div><Settings size={21}/><div><h2>Application & environment configuration</h2><p>DevOps Admin maintains the server data that previously lived in inventory and vars files.</p></div></div>
        <button className="secondary-button" type="button" onClick={() => beginEnvironment()}><Plus size={15}/>Add environment</button>
      </div>

      <div className="datasource-environment-list">
        {environments.map((item) => <button type="button" key={item.id} onClick={() => beginEnvironment(item)}>
          <span><strong>{item.application}</strong><small>{item.environment.toUpperCase()} · {item.instance_name}</small></span>
          <span><strong>{item.admin_host}:{item.admin_port}</strong><small>{item.domain_name}</small></span>
          <span className={item.weblogic_password_configured && item.ssh_password_configured ? "credential-ok" : "credential-missing"}>
            {item.weblogic_password_configured && item.ssh_password_configured ? "Credentials configured" : "Credentials incomplete"}
          </span>
        </button>)}
        {environments.length === 0 && <div className="datasource-empty">No application environments configured yet. Add the first environment from this page.</div>}
      </div>
    </section>}

    {isAdmin && showConfig && <form className="datasource-config-form form-card" onSubmit={saveEnvironment}>
      <div className="full-width datasource-section-title">
        <div><Server size={21}/><div><h2>{editingEnvironmentId ? "Update application environment" : "Add application environment"}</h2><p>Passwords are encrypted in the database and are never shown back in the dashboard.</p></div></div>
      </div>

      <label>Application
        <select required value={environmentForm.application} onChange={(e) => {
          const application = e.target.value;
          setEnvironmentForm({ ...environmentForm, application });
        }}>
          {applications.map((item) => <option key={item.id} value={item.code}>{item.display_name}</option>)}
        </select>
      </label>
      <label>Environment<input required value={environmentForm.environment} onChange={(e) => setEnvironmentForm({ ...environmentForm, environment: e.target.value.toLowerCase() })} placeholder="txcsit"/></label>
      <label>Instance<input required value={environmentForm.instance_name} onChange={(e) => setEnvironmentForm({ ...environmentForm, instance_name: e.target.value.toLowerCase() })} placeholder="app1"/></label>
      <label>Inventory hostname<input required value={environmentForm.inventory_hostname} onChange={(e) => setEnvironmentForm({ ...environmentForm, inventory_hostname: e.target.value })} placeholder="obp_txcsit_app1"/></label>
      <label>Domain<input required value={environmentForm.domain_name} onChange={(e) => setEnvironmentForm({ ...environmentForm, domain_name: e.target.value })} placeholder="TXOBPSIT"/></label>

      <label>BASE<input required value={environmentForm.base_path} onChange={(e) => changeBasePath(e.target.value)} placeholder="/obpay"/></label>
      <label>Admin / Ansible host<input required value={environmentForm.admin_host} onChange={(e) => setEnvironmentForm({ ...environmentForm, admin_host: e.target.value })} placeholder="172.24.x.x"/></label>
      <label>WebLogic port<input type="number" min={1} max={65535} required value={environmentForm.admin_port} onChange={(e) => setEnvironmentForm({ ...environmentForm, admin_port: Number(e.target.value) })}/></label>
      <label>SSH port<input type="number" min={1} max={65535} required value={environmentForm.ssh_port} onChange={(e) => setEnvironmentForm({ ...environmentForm, ssh_port: Number(e.target.value) })}/></label>

      <label className="full-width">WLST executable
        <input required value={environmentForm.wlst_path} onChange={(e) => setEnvironmentForm({ ...environmentForm, wlst_path: e.target.value })} placeholder="/obpay/Oracle/Middleware/Oracle_Home/oracle_common/common/bin/wlst.sh"/>
        <small>The full executable path is stored, not only the common/bin directory.</small>
      </label>

      <label>Artifacts root<input required value={environmentForm.artifacts_location} onChange={(e) => setEnvironmentForm({ ...environmentForm, artifacts_location: e.target.value })} placeholder="/azure_artifact"/></label>
      <label>ENV_NAME<input readOnly value={environmentForm.environment}/></label>
      <label>COMMON_ARTIFACTS_LOCATION<input readOnly value={artifactPreview.common}/></label>
      <label>CZ_CONFIG_LOCATION<input readOnly value={artifactPreview.channel}/></label>
      <label className="full-width">EAR_PATH<input readOnly value={artifactPreview.ear}/></label>

      <label>Azure agent pool<input required value={environmentForm.agent_pool} onChange={(e) => setEnvironmentForm({ ...environmentForm, agent_pool: e.target.value })}/></label>
      <label>WebLogic user<input required value={environmentForm.weblogic_username} onChange={(e) => setEnvironmentForm({ ...environmentForm, weblogic_username: e.target.value })}/></label>
      <label>WebLogic password
        <input type="password" value={environmentForm.weblogic_password || ""} onChange={(e) => setEnvironmentForm({ ...environmentForm, weblogic_password: e.target.value })} autoComplete="new-password" data-lpignore="true" data-1p-ignore="true" placeholder={editingEnvironmentId ? "••••••••  Leave blank to keep current" : "Required before execution"}/>
      </label>
      <label>Ansible / SSH user<input required value={environmentForm.ssh_username} onChange={(e) => setEnvironmentForm({ ...environmentForm, ssh_username: e.target.value })}/></label>
      <label>Ansible / SSH password
        <input type="password" value={environmentForm.ssh_password || ""} onChange={(e) => setEnvironmentForm({ ...environmentForm, ssh_password: e.target.value })} autoComplete="new-password" data-lpignore="true" data-1p-ignore="true" placeholder={editingEnvironmentId ? "••••••••  Leave blank to keep current" : "Required before execution"}/>
      </label>

      <label className="datasource-checkbox"><input type="checkbox" checked={environmentForm.is_production} onChange={(e) => setEnvironmentForm({ ...environmentForm, is_production: e.target.checked })}/>Production environment</label>
      <label className="datasource-checkbox"><input type="checkbox" checked={environmentForm.is_active} onChange={(e) => setEnvironmentForm({ ...environmentForm, is_active: e.target.checked })}/>Active</label>

      <div className="full-width datasource-form-actions datasource-admin-actions">
        <button className="primary-button" disabled={busy}><Save size={15}/>{busy ? "Saving..." : editingEnvironmentId ? "Update Database" : "Save to Database"}</button>
        <button className="secondary-button" type="button" disabled={busy} onClick={() => applyTxcsitPreset()}>Load TXCSIT Defaults</button>
        <button className="secondary-button" type="button" disabled={busy} onClick={() => setShowConfig(false)}>Cancel</button>
      </div>
    </form>}

    <section className="datasource-workspace">
      <div className="datasource-section-title">
        <div><Eye size={21}/><div><h2>Create datasources for an entity</h2><p>Select the application and environment first. The stored WebLogic configuration is shown before datasource-specific input is accepted.</p></div></div>
        <button className="secondary-button" type="button" onClick={() => void load()}><RefreshCw size={15}/>Refresh</button>
      </div>

      <form className="form-card datasource-operation-form" onSubmit={preview}>
        <label>Application
          <select required value={selectedApplication} onChange={(e) => setSelectedApplication(e.target.value)}>
            <option value="">Select application</option>
            {applications.map((item) => <option key={item.id} value={item.code}>{item.display_name}</option>)}
          </select>
        </label>

        <label>Environment
          <select required value={environmentId || ""} onChange={(e) => setEnvironmentId(Number(e.target.value))}>
            <option value="">Select environment</option>
            {applicationEnvironments.map((item) => <option key={item.id} value={item.id}>{item.environment.toUpperCase()} · {item.instance_name}</option>)}
          </select>
        </label>

        {!applicationEnvironments.length && selectedApplication && <div className="full-width datasource-empty">No active environment has been configured for {selectedApplication}. A DevOps Admin must add it first.</div>}

        {selectedEnvironment && <div className="full-width datasource-runtime-config">
          <div><small>Application</small><strong>{selectedEnvironment.application}</strong></div>
          <div><small>ENV_NAME</small><strong>{selectedEnvironment.environment}</strong></div>
          <div><small>BASE</small><strong>{selectedEnvironment.base_path}</strong></div>
          <div><small>Inventory Host</small><strong>{selectedEnvironment.inventory_hostname}</strong></div>
          <div><small>Domain</small><strong>{selectedEnvironment.domain_name}</strong></div>
          <div><small>Admin / Ansible Host</small><strong>{selectedEnvironment.admin_host}</strong></div>
          <div><small>WebLogic Port</small><strong>{selectedEnvironment.admin_port}</strong></div>
          <div><small>WLST</small><strong>{selectedEnvironment.wlst_path}</strong></div>
          <div><small>Agent Pool</small><strong>{selectedEnvironment.agent_pool}</strong></div>
          <div><small>ARTIFACTS_LOCATION</small><strong>{selectedEnvironment.artifacts_location}</strong></div>
          <div><small>COMMON_ARTIFACTS_LOCATION</small><strong>{selectedEnvironment.common_artifacts_location}</strong></div>
          <div><small>CZ_CONFIG_LOCATION</small><strong>{selectedEnvironment.cz_config_location}</strong></div>
          <div><small>EAR_PATH</small><strong>{selectedEnvironment.ear_path}</strong></div>
          <div><small>WebLogic User</small><strong>{selectedEnvironment.weblogic_username || "Not configured"}</strong></div>
          <div><small>WebLogic Password</small><strong>{selectedEnvironment.weblogic_password_configured ? "••••••••" : "Not configured"}</strong></div>
          <div><small>Ansible / SSH User</small><strong>{selectedEnvironment.ssh_username || "Not configured"}</strong></div>
          <div><small>Ansible / SSH Password</small><strong>{selectedEnvironment.ssh_password_configured ? "••••••••" : "Not configured"}</strong></div>
          <div><small>Default DB Host</small><strong>{selectedEnvironment.default_db_host || "Not configured"}</strong></div>
          <div><small>Default DB Port</small><strong>{selectedEnvironment.default_db_port || "Not configured"}</strong></div>
          <div><small>Default ONS Nodes</small><strong>{selectedEnvironment.default_ons_nodes || "Not configured"}</strong></div>
        </div>}

        <div className="full-width datasource-subheading">
          <strong>Datasource details</strong>
          <span>These values are specific to the entity you are creating.</span>
        </div>

        <label>Reference entity<input required value={referenceEntity} onChange={(e) => setReferenceEntity(e.target.value.toUpperCase())} placeholder="QA"/></label>
        <label>Target entity<input required value={targetEntity} onChange={(e) => setTargetEntity(e.target.value.toUpperCase())} placeholder="IN" list="configured-datasource-entities"/></label>
        <datalist id="configured-datasource-entities">{selectedEnvironment?.entities.map((item) => <option key={item.id} value={item.entity_code}/>)}</datalist>
        <label>Datasource type<select value={datasourceType} onChange={(e) => setDatasourceType(e.target.value as "standalone" | "gridlink")}><option value="standalone">Standalone</option><option value="gridlink">GridLink</option></select></label>

        <label>Database host<input required value={dbHost} onChange={(e) => setDbHost(e.target.value)} placeholder="gtbtxcoreobpmdbsit.uat.mashreqdev.com"/></label>
        <label>Database port<input type="number" min={1} max={65535} required value={dbPort} onChange={(e) => setDbPort(Number(e.target.value))}/></label>
        <label>Service ID<input required value={serviceId} onChange={(e) => setServiceId(e.target.value)} placeholder="TXPMINS"/></label>
        <label>Schema user<input required value={schemaUsername} onChange={(e) => setSchemaUsername(e.target.value.toUpperCase())} placeholder="OBPIN"/></label>

        <label className="full-width">Schema password pattern
          <input type="password" value={passwordPattern} onChange={(e) => setPasswordPattern(e.target.value)} autoComplete="new-password" data-lpignore="true" data-1p-ignore="true" placeholder={existingTargetProfile?.password_pattern_configured ? "Leave blank to reuse encrypted saved pattern" : "{username}_TXS1T"}/>
          <small>Use {"{username}"} where the schema user should be inserted. The value is encrypted before it is stored.</small>
        </label>

        {datasourceType === "gridlink" && <label className="full-width">ONS nodes<input required value={onsNodes} onChange={(e) => setOnsNodes(e.target.value)} placeholder="host1:6200,host2:6200"/></label>}

        <label className="full-width">Azure DevOps PAT
          <input type="password" name="datasource-azure-devops-pat" value={pat} onChange={(e) => setPat(e.target.value)} onFocus={() => setPatEditable(true)} readOnly={!patEditable} autoComplete="new-password" data-lpignore="true" data-1p-ignore="true" spellCheck={false} placeholder="PAT is kept only for this browser session"/>
        </label>

        <div className="full-width datasource-form-actions">
          <button className="primary-button" disabled={!canPreview}><Eye size={15}/>{busy ? "Running pipeline..." : "Preview from WebLogic"}</button>
        </div>
      </form>
    </section>

    {plan && selectedOperation && <section className="datasource-plan">
      <div className="datasource-section-title">
        <div><Database size={21}/><div><h2>{selectedOperation.status === "Completed" ? "Creation overview" : `Preview · ${selectedOperation.request_id}`}</h2><p>{plan.application} / {plan.environment.toUpperCase()} · {plan.reference_entity} → {plan.target_entity}</p></div></div>
        <span className={`status ${statusClass(selectedOperation.status)}`}>{selectedOperation.status}</span>
      </div>

      {selectedOperation.status === "Completed" && <div className="datasource-created-summary">
        <div><small>Datasources created</small><strong>{plan.summary?.created_count ?? createdItems.length}</strong></div>
        <div><small>Target entity</small><strong>{selectedOperation.target_entity}</strong></div>
        <div><small>Schema user</small><strong>{selectedOperation.schema_username}</strong></div>
        <div><small>Pipeline run</small><strong>#{selectedOperation.azure_run_id || "—"}</strong></div>
        <div className="full-width"><small>Datasource names</small><strong>{(plan.summary?.created_names?.length ? plan.summary.created_names : createdItems.map((item) => item.target_name)).join(", ") || "—"}</strong></div>
      </div>}

      <div className="table-card">
        <table>
          <thead><tr><th>Reference</th><th>Datasource</th><th>JNDI</th><th>Schema</th><th>Database</th><th>Targets</th><th>Type</th><th>Status</th></tr></thead>
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
        {selectedOperation.azure_run_url && <a href={selectedOperation.azure_run_url} target="_blank" rel="noreferrer"><ExternalLink size={15}/>Open Azure DevOps run</a>}
        {selectedOperation.status === "Previewed" && <button className="primary-button" disabled={busy || plan.datasources.some((item) => item.status !== "Ready")} onClick={() => setConfirmApply(true)}>Create Datasources</button>}
      </div>
    </section>}

    <section className="datasource-history">
      <div className="datasource-section-title"><div><Database size={21}/><div><h2>Recent datasource operations</h2><p>Preview and creation history. Passwords and password patterns are never returned in this view.</p></div></div></div>
      <div className="table-card">
        <table>
          <thead><tr><th>Request</th><th>Reference → Target</th><th>Schema</th><th>Type</th><th>Requested by</th><th>Status</th><th>Updated</th><th>Run</th></tr></thead>
          <tbody>{operations.map((item) => <tr key={item.id} onClick={() => item.preview && setSelectedOperation(item)} className={item.preview ? "datasource-history-clickable" : ""}>
            <td><strong>{item.request_id}</strong></td>
            <td>{item.reference_entity} → <strong>{item.target_entity}</strong></td>
            <td>{item.schema_username || "—"}</td>
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
      message="This will trigger the datasource pipeline and apply the previewed changes to the selected WebLogic environment through WLST."
      details={[
        { label: "Request", value: selectedOperation?.request_id || "" },
        { label: "Environment", value: selectedEnvironment ? `${selectedEnvironment.application} / ${selectedEnvironment.environment.toUpperCase()}` : "" },
        { label: "Entity", value: selectedOperation ? `${selectedOperation.reference_entity} → ${selectedOperation.target_entity}` : "" },
        { label: "Schema", value: selectedOperation?.schema_username || "" },
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
