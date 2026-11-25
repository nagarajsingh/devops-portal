import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Boxes,
  Database,
  AlertTriangle,
  CheckCircle2,
  Download,
  Eye,
  EyeOff,
  FileSpreadsheet,
  FileText,
  History,
  KeyRound,
  Layers3,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings2,
  ShieldCheck,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import {
  createInventoryApplication,
  createInventoryEnvironment,
  createInventoryRecord,
  deleteInventoryRecord,
  getInventoryApplications,
  getInventoryEnvironments,
  getInventoryRecords,
  getInventorySummary,
  getInventoryPatchingSummary,
  downloadInventoryExport,
  previewInventoryExcel,
  commitInventoryExcel,
  revealInventoryCredential,
  updateInventoryRecord,
  type InventoryRecordInput,
} from "../services/api";
import InventoryCatalogManager from "../components/InventoryCatalogManager";
import InventoryHistoryModal from "../components/InventoryHistoryModal";
import InventoryGlobalSearch from "./InventoryGlobalSearch";
import MicroservicesInventory from "./MicroservicesInventory";
import PatchingInventory from "./PatchingInventory";
import type {
  InventoryApplication,
  InventoryCategory,
  InventoryCategorySummary,
  InventoryEnvironment,
  InventoryImportPreview,
  InventoryPatchingSummary,
  InventoryRecord,
} from "../types";

type Notice = { variant: "success" | "error" | "info"; message: string };

const emptyRecord = (applicationId = 0, environmentId = 0): InventoryRecordInput => ({
  application_id: applicationId,
  environment_id: environmentId,
  ip_address: "",
  hostname: "",
  asset_type: "",
  app_name: "",
  ssh_username: "",
  ssh_password: "",
  application_username: "",
  application_password: "",
  console_details: "",
  notes: "",
});

function formatDate(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function categoryTitle(category: InventoryCategory) {
  return category === "GTB" ? "GTB" : "Microservices";
}

export default function InventoryPage({ token }: { token: string }) {
  const [summaries, setSummaries] = useState<InventoryCategorySummary[]>([]);
  const [environments, setEnvironments] = useState<InventoryEnvironment[]>([]);
  const [microserviceEnvironments, setMicroserviceEnvironments] = useState<InventoryEnvironment[]>([]);
  const [category, setCategory] = useState<InventoryCategory | null>(null);
  const [patchingOpen, setPatchingOpen] = useState(false);
  const [patchingSummary, setPatchingSummary] = useState<InventoryPatchingSummary | null>(null);
  const [applications, setApplications] = useState<InventoryApplication[]>([]);
  const [selectedApplication, setSelectedApplication] = useState<InventoryApplication | null>(null);
  const [records, setRecords] = useState<InventoryRecord[]>([]);
  const [environmentId, setEnvironmentId] = useState<number>(0);
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [loading, setLoading] = useState(true);
  const [recordsLoading, setRecordsLoading] = useState(false);

  const [recordFormOpen, setRecordFormOpen] = useState(false);
  const [editingRecordId, setEditingRecordId] = useState<number | null>(null);
  const [recordForm, setRecordForm] = useState<InventoryRecordInput>(emptyRecord());
  const [savingRecord, setSavingRecord] = useState(false);

  const [detailRecord, setDetailRecord] = useState<InventoryRecord | null>(null);
  const [revealed, setRevealed] = useState<{ SSH?: string; APPLICATION?: string }>({});
  const [revealBusy, setRevealBusy] = useState<"SSH" | "APPLICATION" | null>(null);
  const [tableCredentials, setTableCredentials] = useState<Record<string,string>>({});
  const [tableCredentialBusy, setTableCredentialBusy] = useState<string|null>(null);

  const [catalogOpen, setCatalogOpen] = useState<"application" | "environment" | null>(null);
  const [catalogCode, setCatalogCode] = useState("");
  const [catalogName, setCatalogName] = useState("");
  const [catalogSaving, setCatalogSaving] = useState(false);

  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<InventoryImportPreview | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [exportBusy, setExportBusy] = useState<"xlsx" | "pdf" | null>(null);
  const [catalogManagerOpen,setCatalogManagerOpen]=useState(false);
  const [historyTarget,setHistoryTarget]=useState<{type:string;id?:number;name:string}|null>(null);

  async function loadBase() {
    setLoading(true);
    setNotice(null);
    try {
      const [summaryResult, environmentRows, microserviceEnvironmentRows, patchSummary] = await Promise.all([
        getInventorySummary(token),
        getInventoryEnvironments(token, "GTB"),
        getInventoryEnvironments(token, "MICROSERVICES"),
        getInventoryPatchingSummary(token),
      ]);
      setSummaries(summaryResult.categories);
      setEnvironments(environmentRows);
      setMicroserviceEnvironments(microserviceEnvironmentRows);
      setPatchingSummary(patchSummary);
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to load inventory" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadBase(); }, [token]);

  async function openCategory(nextCategory: InventoryCategory) {
    setCategory(nextCategory);
    setSelectedApplication(null);
    setEnvironmentId(0);
    setSearch("");
    setRecords([]);
    setTableCredentials({});
    setNotice(null);
    if (nextCategory === "MICROSERVICES") {
      setApplications([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setApplications(await getInventoryApplications(nextCategory, token));
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to load inventory applications" });
    } finally {
      setLoading(false);
    }
  }

  async function refreshApplications() {
    if (!category) return;
    const rows = await getInventoryApplications(category, token);
    setApplications(rows);
    if (selectedApplication) {
      setSelectedApplication(rows.find((item) => item.id === selectedApplication.id) || selectedApplication);
    }
  }

  async function loadRecords(application: InventoryApplication) {
    setSelectedApplication(application);
    setEnvironmentId(0);
    setSearch("");
    setTableCredentials({});
    setRecordsLoading(true);
    setNotice(null);
    try {
      setRecords(await getInventoryRecords(token, { application_id: application.id }));
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to load inventory records" });
    } finally {
      setRecordsLoading(false);
    }
  }

  async function refreshRecords() {
    if (!selectedApplication) return;
    setRecordsLoading(true);
    try {
      setRecords(await getInventoryRecords(token, { application_id: selectedApplication.id }));
      await Promise.all([refreshApplications(), loadBase()]);
    } finally {
      setRecordsLoading(false);
    }
  }

  const environmentCounts = useMemo(() => {
    const counts = new Map<number, number>();
    records.forEach((item) => counts.set(item.environment_id, (counts.get(item.environment_id) || 0) + 1));
    return counts;
  }, [records]);

  const filteredRecords = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return records.filter((item) => {
      if (environmentId && item.environment_id !== environmentId) return false;
      if (!needle) return true;
      return [
        item.ip_address,
        item.hostname,
        item.asset_type,
        item.app_name,
        item.ssh_username,
        item.application_username,
        item.console_details,
        item.notes,
      ].some((value) => value.toLowerCase().includes(needle));
    });
  }, [records, environmentId, search]);

  function beginCreateRecord() {
    if (!selectedApplication) return;
    const defaultEnvironment = environmentId || environments[0]?.id || 0;
    setEditingRecordId(null);
    setRecordForm(emptyRecord(selectedApplication.id, defaultEnvironment));
    setRecordFormOpen(true);
    setNotice(null);
  }

  function beginEditRecord(record: InventoryRecord) {
    setEditingRecordId(record.id);
    setRecordForm({
      application_id: record.application_id,
      environment_id: record.environment_id,
      ip_address: record.ip_address,
      hostname: record.hostname,
      asset_type: record.asset_type,
      app_name: record.app_name,
      ssh_username: record.ssh_username,
      ssh_password: "",
      application_username: record.application_username,
      application_password: "",
      console_details: record.console_details,
      notes: record.notes,
    });
    setRecordFormOpen(true);
    setDetailRecord(null);
    setRevealed({});
  }

  async function saveRecord(event: FormEvent) {
    event.preventDefault();
    if (!recordForm.application_id || !recordForm.environment_id) return;
    setSavingRecord(true);
    setNotice(null);
    try {
      const payload = {
        ...recordForm,
        ssh_password: recordForm.ssh_password || undefined,
        application_password: recordForm.application_password || undefined,
      };
      const saved = editingRecordId
        ? await updateInventoryRecord(editingRecordId, payload, token)
        : await createInventoryRecord(payload, token);
      setRecordFormOpen(false);
      setEditingRecordId(null);
      setNotice({
        variant: "success",
        message: `${saved.application_code} / ${saved.environment_name} inventory record ${editingRecordId ? "updated" : "created"} successfully.`,
      });
      await refreshRecords();
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to save inventory record" });
    } finally {
      setSavingRecord(false);
    }
  }

  async function removeRecord(record: InventoryRecord) {
    const confirmed = window.confirm(
      `Remove ${record.application_code} / ${record.environment_name} / ${record.hostname || record.ip_address || "record"} from active inventory?`,
    );
    if (!confirmed) return;
    try {
      await deleteInventoryRecord(record.id, token);
      if (detailRecord?.id === record.id) {
        setDetailRecord(null);
        setRevealed({});
      }
      setNotice({ variant: "success", message: "Inventory record removed." });
      await refreshRecords();
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to remove inventory record" });
    }
  }

  async function revealCredential(type: "SSH" | "APPLICATION") {
    if (!detailRecord) return;
    if (revealed[type]) {
      setRevealed((current) => ({ ...current, [type]: undefined }));
      return;
    }
    setRevealBusy(type);
    try {
      const result = await revealInventoryCredential(detailRecord.id, type, token);
      setRevealed((current) => ({ ...current, [type]: result.password }));
      window.setTimeout(() => {
        setRevealed((current) => ({ ...current, [type]: undefined }));
      }, 30000);
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to reveal credential" });
    } finally {
      setRevealBusy(null);
    }
  }

  async function toggleTableCredential(record: InventoryRecord, type: "SSH" | "APPLICATION") {
    const key = record.id + "-" + type;
    if (tableCredentials[key]) {
      setTableCredentials((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
      return;
    }
    const configured = type === "SSH" ? record.ssh_password_configured : record.application_password_configured;
    if (!configured) return;
    setTableCredentialBusy(key);
    try {
      const result = await revealInventoryCredential(record.id, type, token);
      setTableCredentials((current) => ({ ...current, [key]: result.password }));
      window.setTimeout(() => {
        setTableCredentials((current) => {
          if (!current[key]) return current;
          const next = { ...current };
          delete next[key];
          return next;
        });
      }, 30000);
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to reveal credential" });
    } finally {
      setTableCredentialBusy((current) => current === key ? null : current);
    }
  }

  async function saveCatalog(event: FormEvent) {
    event.preventDefault();
    if (!catalogOpen || !catalogCode.trim()) return;
    setCatalogSaving(true);
    setNotice(null);
    try {
      if (catalogOpen === "application") {
        if (!category) return;
        await createInventoryApplication({
          category,
          code: catalogCode.trim(),
          display_name: catalogName.trim() || catalogCode.trim(),
        }, token);
        await refreshApplications();
        await loadBase();
        setNotice({ variant: "success", message: `${catalogCode.trim().toUpperCase()} added to ${categoryTitle(category)} inventory.` });
      } else {
        await createInventoryEnvironment({
          category: "GTB",
          code: catalogCode.trim(),
          display_name: catalogName.trim() || catalogCode.trim(),
        }, token);
        setEnvironments(await getInventoryEnvironments(token, "GTB"));
        setNotice({ variant: "success", message: `${catalogCode.trim().toUpperCase()} environment added.` });
      }
      setCatalogOpen(null);
      setCatalogCode("");
      setCatalogName("");
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to update inventory catalog" });
    } finally {
      setCatalogSaving(false);
    }
  }


  function beginImport() {
    setImportOpen(true);
    setImportFile(null);
    setImportPreview(null);
    setNotice(null);
  }

  async function previewImport(event: FormEvent) {
    event.preventDefault();
    if (!importFile) return;
    setImportBusy(true);
    setNotice(null);
    try {
      setImportPreview(await previewInventoryExcel(importFile, token));
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to preview inventory Excel file" });
    } finally {
      setImportBusy(false);
    }
  }

  async function commitImport() {
    if (!importFile || !importPreview) return;
    setImportBusy(true);
    setNotice(null);
    try {
      const result = await commitInventoryExcel(importFile, token);
      setImportOpen(false);
      setImportFile(null);
      setImportPreview(null);
      await Promise.all([refreshApplications(), loadBase()]);
      setEnvironments(await getInventoryEnvironments(token, "GTB"));
      setNotice({
        variant: "success",
        message: `Excel import completed: ${result.created_count} created, ${result.updated_count} updated, ${result.skipped_count} skipped.`,
      });
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to import inventory Excel file" });
    } finally {
      setImportBusy(false);
    }
  }

  function back() {
    if (selectedApplication) {
      setSelectedApplication(null);
      setRecords([]);
      setTableCredentials({});
      setEnvironmentId(0);
      setSearch("");
      return;
    }
    setCategory(null);
    setApplications([]);
  }

  async function exportGtb(format: "xlsx" | "pdf", applicationId?: number) {
    setExportBusy(format);
    try {
      await downloadInventoryExport("gtb", format, token, {
        application_id: applicationId,
        environment_id: environmentId || undefined,
      });
    } catch (error) {
      setNotice({ variant: "error", message: error instanceof Error ? error.message : "Unable to export GTB inventory" });
    } finally {
      setExportBusy(null);
    }
  }

  if (loading && !category && !patchingOpen) {
    return <div className="inventory-loading">Loading DevOps inventory...</div>;
  }

  return <div className="inventory-page">
    <section className="inventory-hero">
      <div>
        <span className="eyebrow">DEVOPS ASSET CATALOG</span>
        <h1>Inventory</h1>
        <p>One operational catalog for GTB infrastructure, Microservices database configuration and patching lifecycle. Search once across every inventory source.</p>
      </div>
      <div className="inventory-hero-actions"><button type="button" className="secondary-button" onClick={()=>setHistoryTarget({type:"",name:"All inventory changes"})}><History size={16}/>History</button><button type="button" className="secondary-button" onClick={()=>setCatalogManagerOpen(true)}><Settings2 size={16}/>Manage catalog</button><div className="inventory-hero-shield"><ShieldCheck size={30}/><span>DevOps only</span></div></div>
    </section>

    {notice && <div className={`inventory-notice ${notice.variant}`}>{notice.message}</div>}

    {!category && !patchingOpen && <>
      <InventoryGlobalSearch token={token}/>
      <section className="inventory-category-grid inventory-category-grid-three">
        {(["GTB", "MICROSERVICES"] as InventoryCategory[]).map((item) => {
          const summary = summaries.find((row) => row.category === item);
          const Icon = item === "GTB" ? Database : Boxes;
          return <button className="inventory-category-card" key={item} onClick={() => void openCategory(item)}>
            <div className="inventory-card-icon"><Icon size={27}/></div>
            <div className="inventory-category-copy">
              <span className="eyebrow">{item === "GTB" ? "GLOBAL TRANSACTION BANKING" : "PLATFORM WORKLOADS"}</span>
              <h2>{categoryTitle(item)}</h2>
              <p>{item === "GTB" ? "Server, application, database, access and console inventory." : "Group, service, environment and database connection inventory."}</p>
            </div>
            <div className="inventory-card-stats">
              <span><strong>{summary?.application_count ?? 0}</strong> {item === "GTB" ? "Applications" : "Groups"}</span>
              <span><strong>{summary?.record_count ?? 0}</strong> Records</span>
              <span><strong>{summary?.environment_count ?? 0}</strong> Active envs</span>
            </div>
          </button>;
        })}
        <button className="inventory-category-card patching-category-card" onClick={() => setPatchingOpen(true)}>
          <div className="inventory-card-icon"><Wrench size={27}/></div>
          <div className="inventory-category-copy">
            <span className="eyebrow">PATCH MANAGEMENT</span>
            <h2>Patching</h2>
            <p>Quarterly server and cluster patch scope, scheduling, approvals, CR tracking and historical activity.</p>
          </div>
          <div className="inventory-card-stats">
            <span><strong>{patchingSummary?.total_assets ?? 0}</strong> Assets</span>
            <span><strong>{patchingSummary?.environment_counts.PROD ?? 0}</strong> Production</span>
            <span><strong>{patchingSummary?.environment_counts.DR ?? 0}</strong> DR</span>
          </div>
        </button>
      </section>
    </>}

    {patchingOpen && <PatchingInventory token={token} onBack={() => { setPatchingOpen(false); void loadBase(); }}/>}

    {category === "MICROSERVICES" && <MicroservicesInventory
      token={token}
      environments={microserviceEnvironments}
      onBack={() => { setCategory(null); setApplications([]); }}
      onEnvironmentsChange={setMicroserviceEnvironments}
    />}

    {category === "GTB" && !selectedApplication && <>
      <section className="inventory-section-bar">
        <div>
          <button className="inventory-back" onClick={back}><ArrowLeft size={16}/>Inventory</button>
          <span className="eyebrow">{category}</span>
          <h2>{categoryTitle(category)} applications</h2>
          <p>Applications and counts are database-driven. New applications appear here automatically.</p>
        </div>
        <div className="inventory-section-actions">
          <button className="secondary-button" disabled={!!exportBusy} onClick={() => void exportGtb("xlsx")}><Download size={16}/>{exportBusy === "xlsx" ? "Exporting..." : "Excel"}</button>
          <button className="secondary-button" disabled={!!exportBusy} onClick={() => void exportGtb("pdf")}><FileText size={16}/>{exportBusy === "pdf" ? "Exporting..." : "PDF"}</button>
          <button className="secondary-button" onClick={beginImport}><FileSpreadsheet size={16}/>Import Excel</button>
          <button className="secondary-button" onClick={() => { setCatalogOpen("environment"); setCatalogCode(""); setCatalogName(""); }}><Layers3 size={16}/>Add GTB environment</button>
          <button className="primary-button" onClick={() => { setCatalogOpen("application"); setCatalogCode(""); setCatalogName(""); }}><Plus size={16}/>Add application</button>
        </div>
      </section>

      <section className="inventory-application-grid">
        {applications.map((application) => <button className="inventory-application-card" key={application.id} onClick={() => void loadRecords(application)}>
          <div className="inventory-application-top">
            <div className="inventory-card-icon small"><Server size={20}/></div>
            <span>{application.category}</span>
          </div>
          <h3>{application.display_name}</h3>
          <p>{application.code}</p>
          <div className="inventory-application-stats">
            <span><strong>{application.record_count}</strong> records</span>
            <span><strong>{application.environment_count}</strong> environments</span>
          </div>
        </button>)}
      </section>
    </>}

    {category === "GTB" && selectedApplication && <>
      <section className="inventory-section-bar inventory-app-heading">
        <div>
          <button className="inventory-back" onClick={back}><ArrowLeft size={16}/>{categoryTitle(category)}</button>
          <span className="eyebrow">{category} INVENTORY</span>
          <h2>{selectedApplication.display_name}</h2>
          <p>{records.length} active record{records.length === 1 ? "" : "s"} across {environmentCounts.size} configured environment{environmentCounts.size === 1 ? "" : "s"}.</p>
        </div>
        <div className="inventory-section-actions">
          <button className="secondary-button" disabled={!!exportBusy} onClick={() => void exportGtb("xlsx", selectedApplication.id)}><Download size={16}/>{exportBusy === "xlsx" ? "Exporting..." : "Excel"}</button>
          <button className="secondary-button" disabled={!!exportBusy} onClick={() => void exportGtb("pdf", selectedApplication.id)}><FileText size={16}/>{exportBusy === "pdf" ? "Exporting..." : "PDF"}</button>
          <button className="secondary-button" disabled={recordsLoading} onClick={() => void refreshRecords()}><RefreshCw size={16} className={recordsLoading ? "spin" : ""}/>Refresh</button>
          <button className="primary-button" onClick={beginCreateRecord}><Plus size={16}/>Add record</button>
        </div>
      </section>

      <section className="inventory-environment-strip">
        <button className={environmentId === 0 ? "active" : ""} onClick={() => setEnvironmentId(0)}>
          <strong>All</strong><span>{records.length}</span>
        </button>
        {environments.map((environment) => <button
          key={environment.id}
          className={environmentId === environment.id ? "active" : ""}
          onClick={() => setEnvironmentId(environment.id)}
        >
          <strong>{environment.display_name}</strong>
          <span>{environmentCounts.get(environment.id) || 0}</span>
        </button>)}
      </section>

      <section className="inventory-record-panel">
        <div className="inventory-record-toolbar">
          <div className="inventory-search"><Search size={17}/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search IP, hostname, type, app name, user, console or notes..."/></div>
          <span>{filteredRecords.length} shown</span>
        </div>

        <div className="inventory-table-wrap">
          <table className="inventory-table">
            <thead><tr><th>Environment</th><th>IP</th><th>Hostname</th><th>Type</th><th>App Name</th><th>Access</th><th>Updated</th><th/></tr></thead>
            <tbody>
              {filteredRecords.map((record) => <tr key={record.id}>
                <td><span className="inventory-env-badge">{record.environment_name}</span></td>
                <td><strong>{record.ip_address || "—"}</strong></td>
                <td>{record.hostname || "—"}</td>
                <td>{record.asset_type || "—"}</td>
                <td>{record.app_name || "—"}</td>
                <td><div className="inventory-inline-credentials">
                  <div className="inventory-inline-secret compact">
                    <span>SSH</span>
                    <strong className="inventory-inline-username">{record.ssh_username||"—"}</strong>
                    <code>{tableCredentials[record.id+"-SSH"]||(record.ssh_password_configured?"••••••••":"Not configured")}</code>
                    {record.ssh_password_configured&&<button type="button" title={tableCredentials[record.id+"-SSH"]?"Hide SSH password":"Reveal SSH password"} aria-label={tableCredentials[record.id+"-SSH"]?"Hide SSH password":"Reveal SSH password"} disabled={tableCredentialBusy===record.id+"-SSH"} onClick={()=>void toggleTableCredential(record,"SSH")}>
                      {tableCredentialBusy===record.id+"-SSH"?<RefreshCw size={14} className="spin"/>:tableCredentials[record.id+"-SSH"]?<EyeOff size={14}/>:<Eye size={14}/>} 
                    </button>}
                  </div>
                  <div className="inventory-inline-secret compact">
                    <span>APP</span>
                    <strong className="inventory-inline-username">{record.application_username||"—"}</strong>
                    <code>{tableCredentials[record.id+"-APPLICATION"]||(record.application_password_configured?"••••••••":"Not configured")}</code>
                    {record.application_password_configured&&<button type="button" title={tableCredentials[record.id+"-APPLICATION"]?"Hide application password":"Reveal application password"} aria-label={tableCredentials[record.id+"-APPLICATION"]?"Hide application password":"Reveal application password"} disabled={tableCredentialBusy===record.id+"-APPLICATION"} onClick={()=>void toggleTableCredential(record,"APPLICATION")}>
                      {tableCredentialBusy===record.id+"-APPLICATION"?<RefreshCw size={14} className="spin"/>:tableCredentials[record.id+"-APPLICATION"]?<EyeOff size={14}/>:<Eye size={14}/>} 
                    </button>}
                  </div>
                </div></td>
                <td><small>{formatDate(record.updated_at)}</small></td>
                <td><button className="inventory-row-action" onClick={() => { setDetailRecord(record); setRevealed({}); }}><Server size={16}/>View</button></td>
              </tr>)}
              {!recordsLoading && filteredRecords.length === 0 && <tr><td colSpan={8}><div className="inventory-empty">No inventory records match this application/environment selection.</div></td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>}

    {recordFormOpen && <div className="inventory-modal-backdrop" onMouseDown={() => !savingRecord && setRecordFormOpen(false)}>
      <form className="inventory-modal inventory-record-form" onSubmit={saveRecord} onMouseDown={(event) => event.stopPropagation()}>
        <button type="button" className="inventory-modal-close" onClick={() => setRecordFormOpen(false)}><X size={19}/></button>
        <div className="inventory-modal-heading">
          <div className="inventory-card-icon"><Server size={22}/></div>
          <div><span className="eyebrow">{editingRecordId ? "UPDATE RECORD" : "NEW RECORD"}</span><h2>{selectedApplication?.display_name} inventory</h2><p>Passwords are encrypted before storage and are never returned in normal inventory responses.</p></div>
        </div>

        <div className="inventory-form-grid">
          <label>Application
            <select required value={recordForm.application_id} onChange={(event) => setRecordForm((current) => ({ ...current, application_id: Number(event.target.value) }))}>
              {applications.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
            </select>
          </label>
          <label>Environment
            <select required value={recordForm.environment_id} onChange={(event) => setRecordForm((current) => ({ ...current, environment_id: Number(event.target.value) }))}>
              <option value={0}>Select environment</option>
              {environments.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
            </select>
          </label>
          <label>IP address<input value={recordForm.ip_address} onChange={(event) => setRecordForm((current) => ({ ...current, ip_address: event.target.value }))} placeholder="172.24.x.x"/></label>
          <label>Hostname<input value={recordForm.hostname} onChange={(event) => setRecordForm((current) => ({ ...current, hostname: event.target.value }))} placeholder="GTB..."/></label>
          <label>Type<input value={recordForm.asset_type} onChange={(event) => setRecordForm((current) => ({ ...current, asset_type: event.target.value }))} placeholder="APP SERVER / WEB SERVER / DATABASE SERVER"/></label>
          <label>App Name<input value={recordForm.app_name} onChange={(event) => setRecordForm((current) => ({ ...current, app_name: event.target.value }))} placeholder="AdminServer / component name"/></label>

          <div className="inventory-form-divider"><KeyRound size={16}/>SSH access</div>
          <label>SSH username<input value={recordForm.ssh_username} onChange={(event) => setRecordForm((current) => ({ ...current, ssh_username: event.target.value }))}/></label>
          <label>SSH password<input type="password" autoComplete="new-password" value={recordForm.ssh_password || ""} onChange={(event) => setRecordForm((current) => ({ ...current, ssh_password: event.target.value }))} placeholder={editingRecordId ? "Leave blank to keep current password" : "Optional"}/></label>

          <div className="inventory-form-divider"><ShieldCheck size={16}/>Application access</div>
          <label>Application username<input value={recordForm.application_username} onChange={(event) => setRecordForm((current) => ({ ...current, application_username: event.target.value }))}/></label>
          <label>Application password<input type="password" autoComplete="new-password" value={recordForm.application_password || ""} onChange={(event) => setRecordForm((current) => ({ ...current, application_password: event.target.value }))} placeholder={editingRecordId ? "Leave blank to keep current password" : "Optional"}/></label>

          <label className="full-width">Console details<textarea rows={3} value={recordForm.console_details} onChange={(event) => setRecordForm((current) => ({ ...current, console_details: event.target.value }))} placeholder="Console URL, port, connection details..."/></label>
          <label className="full-width">Notes<textarea rows={3} value={recordForm.notes} onChange={(event) => setRecordForm((current) => ({ ...current, notes: event.target.value }))} placeholder="Operational notes..."/></label>
        </div>

        <div className="inventory-modal-footer">
          <button type="button" className="secondary-button" onClick={() => setRecordFormOpen(false)}>Cancel</button>
          <button type="submit" className="primary-button" disabled={savingRecord || !recordForm.environment_id}>{savingRecord ? "Saving..." : editingRecordId ? "Update record" : "Create record"}</button>
        </div>
      </form>
    </div>}

    {detailRecord && <div className="inventory-modal-backdrop" onMouseDown={() => { setDetailRecord(null); setRevealed({}); }}>
      <article className="inventory-modal inventory-detail" onMouseDown={(event) => event.stopPropagation()}>
        <button type="button" className="inventory-modal-close" onClick={() => { setDetailRecord(null); setRevealed({}); }}><X size={19}/></button>
        <div className="inventory-modal-heading">
          <div className="inventory-card-icon"><Server size={22}/></div>
          <div><span className="eyebrow">{detailRecord.application_code} / {detailRecord.environment_name}</span><h2>{detailRecord.hostname || detailRecord.ip_address || "Inventory record"}</h2><p>{detailRecord.asset_type || "Unclassified asset"} · record #{detailRecord.id}</p></div>
        </div>

        <div className="inventory-detail-grid">
          <div><span>Application</span><strong>{detailRecord.application_name}</strong></div>
          <div><span>Environment</span><strong>{detailRecord.environment_name}</strong></div>
          <div><span>IP Address</span><strong>{detailRecord.ip_address || "—"}</strong></div>
          <div><span>Hostname</span><strong>{detailRecord.hostname || "—"}</strong></div>
          <div><span>Type</span><strong>{detailRecord.asset_type || "—"}</strong></div>
          <div><span>App Name</span><strong>{detailRecord.app_name || "—"}</strong></div>
        </div>

        <section className="inventory-secret-section">
          <h3><KeyRound size={17}/>SSH access</h3>
          <div className="inventory-secret-row"><span>Username</span><strong>{detailRecord.ssh_username || "—"}</strong></div>
          <div className="inventory-secret-row">
            <span>Password</span>
            <code>{revealed.SSH || (detailRecord.ssh_password_configured ? "••••••••••••" : "Not configured")}</code>
            {detailRecord.ssh_password_configured && <button onClick={() => void revealCredential("SSH")}>{revealed.SSH ? <EyeOff size={15}/> : <Eye size={15}/>} {revealBusy === "SSH" ? "Loading..." : revealed.SSH ? "Hide" : "Reveal"}</button>}
          </div>
        </section>

        <section className="inventory-secret-section">
          <h3><ShieldCheck size={17}/>Application access</h3>
          <div className="inventory-secret-row"><span>Username</span><strong>{detailRecord.application_username || "—"}</strong></div>
          <div className="inventory-secret-row">
            <span>Password</span>
            <code>{revealed.APPLICATION || (detailRecord.application_password_configured ? "••••••••••••" : "Not configured")}</code>
            {detailRecord.application_password_configured && <button onClick={() => void revealCredential("APPLICATION")}>{revealed.APPLICATION ? <EyeOff size={15}/> : <Eye size={15}/>} {revealBusy === "APPLICATION" ? "Loading..." : revealed.APPLICATION ? "Hide" : "Reveal"}</button>}
          </div>
          {(revealed.SSH || revealed.APPLICATION) && <small className="inventory-secret-warning">Revealed credentials automatically hide after 30 seconds. Credential reveal is audit logged.</small>}
        </section>

        <section className="inventory-detail-block"><span>Console details</span><pre>{detailRecord.console_details || "—"}</pre></section>
        <section className="inventory-detail-block"><span>Notes</span><p>{detailRecord.notes || "—"}</p></section>

        <div className="inventory-detail-meta">
          <span>Updated by <strong>{detailRecord.updated_by}</strong></span>
          <span>{formatDate(detailRecord.updated_at)}</span>
        </div>

        <div className="inventory-modal-footer">
          <button className="secondary-button" onClick={()=>setHistoryTarget({type:"GTB_RECORD",id:detailRecord.id,name:detailRecord.hostname||detailRecord.ip_address||"Inventory record"})}><History size={15}/>History</button>
          <button className="danger-button" onClick={() => void removeRecord(detailRecord)}><Trash2 size={15}/>Remove</button>
          <button className="primary-button" onClick={() => beginEditRecord(detailRecord)}><Pencil size={15}/>Edit record</button>
        </div>
      </article>
    </div>}

    {importOpen && <div className="inventory-modal-backdrop" onMouseDown={() => !importBusy && setImportOpen(false)}>
      <form className="inventory-modal inventory-import-modal" onSubmit={previewImport} onMouseDown={(event) => event.stopPropagation()}>
        <button type="button" className="inventory-modal-close" onClick={() => !importBusy && setImportOpen(false)}><X size={19}/></button>
        <div className="inventory-modal-heading">
          <div className="inventory-card-icon"><FileSpreadsheet size={22}/></div>
          <div>
            <span className="eyebrow">GTB INVENTORY IMPORT</span>
            <h2>Import Excel inventory</h2>
            <p>Preview the workbook first. Password values are never shown in preview and are encrypted before database storage.</p>
          </div>
        </div>

        <label className="inventory-import-drop">
          <FileSpreadsheet size={30}/>
          <strong>{importFile ? importFile.name : "Choose an .xlsx inventory workbook"}</strong>
          <span>{importFile ? `${(importFile.size / 1024 / 1024).toFixed(2)} MB` : "Maximum file size 15 MB"}</span>
          <input
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(event) => {
              const file = event.target.files?.[0] || null;
              setImportFile(file);
              setImportPreview(null);
            }}
          />
        </label>

        {!importPreview && <div className="inventory-import-security">
          <ShieldCheck size={17}/>
          <div><strong>Credential-safe import</strong><span>The uploaded workbook is processed in memory and is not stored on NFS. SSH and application passwords are encrypted before persistence.</span></div>
        </div>}

        {importPreview && <>
          <div className="inventory-import-stats">
            <div><strong>{importPreview.total_rows}</strong><span>Total rows</span></div>
            <div><strong>{importPreview.ready_rows}</strong><span>Ready</span></div>
            <div><strong>{importPreview.application_count}</strong><span>Applications</span></div>
            <div><strong>{importPreview.environment_count}</strong><span>Environments</span></div>
            <div className={importPreview.invalid_rows ? "warning" : ""}><strong>{importPreview.invalid_rows}</strong><span>Invalid</span></div>
            <div className={importPreview.warning_count ? "warning" : ""}><strong>{importPreview.warning_count}</strong><span>Warnings</span></div>
          </div>

          <div className="inventory-import-summary">
            <div><CheckCircle2 size={16}/><span>Sheet <strong>{importPreview.sheet_name}</strong> · header row {importPreview.header_row}</span></div>
            <div><span>Applications</span><p>{importPreview.applications.join(", ")}</p></div>
            <div><span>Environments</span><p>{importPreview.environments.join(", ")}</p></div>
          </div>

          {importPreview.warnings.length > 0 && <div className="inventory-import-warnings">
            <div className="inventory-import-warning-title"><AlertTriangle size={16}/>Review warnings before import</div>
            <div className="inventory-import-warning-list">
              {importPreview.warnings.slice(0, 20).map((warning, index) => <p key={index}>{warning}</p>)}
              {importPreview.warnings.length > 20 && <p>+ {importPreview.warnings.length - 20} more warnings</p>}
            </div>
          </div>}

          <div className="inventory-import-preview-table">
            <table className="inventory-table">
              <thead><tr><th>Row</th><th>Environment</th><th>Application</th><th>IP</th><th>Hostname</th><th>Type</th><th>App Name</th><th>Credentials</th></tr></thead>
              <tbody>
                {importPreview.preview_rows.map((row) => <tr key={row.source_row}>
                  <td>{row.source_row}</td>
                  <td><span className="inventory-env-badge">{row.environment || "—"}</span></td>
                  <td><strong>{row.application || "—"}</strong></td>
                  <td>{row.ip_address || "—"}</td>
                  <td>{row.hostname || "—"}</td>
                  <td>{row.asset_type || "—"}</td>
                  <td>{row.app_name || "—"}</td>
                  <td><div className="inventory-access-flags">
                    <span className={row.ssh_password_configured ? "configured" : ""}>SSH</span>
                    <span className={row.application_password_configured ? "configured" : ""}>APP</span>
                  </div></td>
                </tr>)}
              </tbody>
            </table>
            {importPreview.preview_truncated && <small>Preview limited to the first {importPreview.preview_rows.length} rows. All validated rows will be processed during import.</small>}
          </div>
        </>}

        <div className="inventory-modal-footer">
          <button type="button" className="secondary-button" disabled={importBusy} onClick={() => setImportOpen(false)}>Cancel</button>
          {!importPreview
            ? <button type="submit" className="primary-button" disabled={!importFile || importBusy}>{importBusy ? "Validating..." : "Preview import"}</button>
            : <>
              <button type="button" className="secondary-button" disabled={importBusy} onClick={() => setImportPreview(null)}>Choose another file</button>
              <button type="button" className="primary-button" disabled={importBusy || importPreview.ready_rows === 0} onClick={() => void commitImport()}>{importBusy ? "Importing..." : `Import ${importPreview.ready_rows} ready rows`}</button>
            </>}
        </div>
      </form>
    </div>}

    {catalogManagerOpen&&<InventoryCatalogManager token={token} onClose={()=>setCatalogManagerOpen(false)} onChanged={()=>void loadBase()}/>}
    {historyTarget&&<InventoryHistoryModal token={token} entityType={historyTarget.type} entityId={historyTarget.id} entityName={historyTarget.name} onClose={()=>setHistoryTarget(null)}/>}

    {catalogOpen && <div className="inventory-modal-backdrop" onMouseDown={() => setCatalogOpen(null)}>
      <form className="inventory-modal inventory-catalog-form" onSubmit={saveCatalog} onMouseDown={(event) => event.stopPropagation()}>
        <button type="button" className="inventory-modal-close" onClick={() => setCatalogOpen(null)}><X size={19}/></button>
        <span className="eyebrow">INVENTORY CATALOG</span>
        <h2>{catalogOpen === "environment" ? "Add GTB environment" : `Add ${catalogOpen}`}</h2>
        <p>This becomes available immediately without a portal code change.</p>
        <label>Code / Name<input autoFocus required value={catalogCode} onChange={(event) => setCatalogCode(event.target.value)} placeholder={catalogOpen === "application" ? "Example: FLEXCUBE" : "Example: R2UAT"}/></label>
        <label>Display name <small>(optional)</small><input value={catalogName} onChange={(event) => setCatalogName(event.target.value)} placeholder="Friendly display name"/></label>
        <div className="inventory-modal-footer">
          <button type="button" className="secondary-button" onClick={() => setCatalogOpen(null)}>Cancel</button>
          <button type="submit" className="primary-button" disabled={catalogSaving}>{catalogSaving ? "Adding..." : "Add"}</button>
        </div>
      </form>
    </div>}
  </div>;
}
