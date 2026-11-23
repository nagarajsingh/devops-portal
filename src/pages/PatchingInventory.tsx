import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Download,
  FileSpreadsheet,
  FileText,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Server,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import {
  commitInventoryPatchingExcel,
  createInventoryPatchCycle,
  createInventoryPatchingAsset,
  deleteInventoryPatchingAsset,
  downloadInventoryExport,
  getInventoryPatchCycles,
  getInventoryPatchingAssets,
  getInventoryPatchingSummary,
  previewInventoryPatchingExcel,
  saveInventoryPatchActivity,
  updateInventoryPatchingAsset,
  type InventoryPatchActivityInput,
  type InventoryPatchingAssetInput,
} from "../services/api";
import type {
  InventoryPatchCycle,
  InventoryPatchEnvironmentClass,
  InventoryPatchingAsset,
  InventoryPatchingImportPreview,
  InventoryPatchingSummary,
  InventoryPatchStatus,
} from "../types";

type Notice={variant:"success"|"error"|"info";message:string};
type Props={token:string;onBack:()=>void};

const emptyAsset:InventoryPatchingAssetInput={
  asset_identifier:"",
  hostname:"",
  application:"",
  application_owner:"",
  asset_type:"",
  environment_name:"",
  environment_class:"NON_PROD",
};

const emptyActivity:InventoryPatchActivityInput={
  previous_patched_date:"",
  planned_date:"",
  status:"NOT_STARTED",
  app_team_approval:"",
  cr_number:"",
  comments:"",
  patch_role:"",
};

const STATUS_LABELS:Record<InventoryPatchStatus,string>={
  NOT_STARTED:"Not Started",
  SCHEDULED:"Scheduled",
  IN_PROGRESS:"In Progress",
  COMPLETED:"Completed",
  BLOCKED:"Blocked",
};

function dateText(value?:string){if(!value)return "—";const parsed=new Date(value);return Number.isNaN(parsed.getTime())?value:parsed.toLocaleDateString();}
function classLabel(value:InventoryPatchEnvironmentClass){return value==="NON_PROD"?"NON-PROD":value;}

export default function PatchingInventory({token,onBack}:Props){
  const [cycles,setCycles]=useState<InventoryPatchCycle[]>([]);
  const [cycleId,setCycleId]=useState(0);
  const [summary,setSummary]=useState<InventoryPatchingSummary|null>(null);
  const [assets,setAssets]=useState<InventoryPatchingAsset[]>([]);
  const [environmentClass,setEnvironmentClass]=useState<""|InventoryPatchEnvironmentClass>("");
  const [status,setStatus]=useState<""|InventoryPatchStatus>("");
  const [search,setSearch]=useState("");
  const [loading,setLoading]=useState(true);
  const [notice,setNotice]=useState<Notice|null>(null);

  const [formOpen,setFormOpen]=useState(false);
  const [editingAsset,setEditingAsset]=useState<InventoryPatchingAsset|null>(null);
  const [assetForm,setAssetForm]=useState<InventoryPatchingAssetInput>(emptyAsset);
  const [activityForm,setActivityForm]=useState<InventoryPatchActivityInput>(emptyActivity);
  const [saving,setSaving]=useState(false);

  const [detail,setDetail]=useState<InventoryPatchingAsset|null>(null);
  const [importOpen,setImportOpen]=useState(false);
  const [importFile,setImportFile]=useState<File|null>(null);
  const [importPreview,setImportPreview]=useState<InventoryPatchingImportPreview|null>(null);
  const [importBusy,setImportBusy]=useState(false);
  const [exportBusy,setExportBusy]=useState<"xlsx"|"pdf"|null>(null);

  async function loadCycles(){
    const rows=await getInventoryPatchCycles(token);
    setCycles(rows);
    setCycleId(current=>current||rows[0]?.id||0);
    return rows;
  }

  async function loadData(selectedCycle=cycleId){
    setLoading(true);setNotice(null);
    try{
      const filters={cycle_id:selectedCycle||undefined,environment_class:environmentClass||undefined,status:status||undefined,q:search.trim()||undefined};
      const [assetRows,summaryRow]=await Promise.all([
        getInventoryPatchingAssets(token,filters),
        getInventoryPatchingSummary(token,selectedCycle||undefined),
      ]);
      setAssets(assetRows);setSummary(summaryRow);
    }catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to load patching inventory"});}
    finally{setLoading(false);}
  }

  useEffect(()=>{loadCycles().then(rows=>void loadData(rows[0]?.id||0)).catch(error=>setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to load patch cycles"}));},[token]);
  useEffect(()=>{if(cycleId)void loadData(cycleId);},[cycleId,environmentClass,status]);

  const currentCycle=cycles.find(item=>item.id===cycleId);
  const filtered=useMemo(()=>{
    const q=search.trim().toLowerCase();
    if(!q)return assets;
    return assets.filter(item=>[
      item.asset_identifier,item.hostname,item.application,item.application_owner,item.asset_type,
      item.environment_name,item.activity?.cr_number||"",item.activity?.comments||"",item.activity?.status||"",
    ].some(value=>value.toLowerCase().includes(q)));
  },[assets,search]);

  async function createCycle(){
    const value=window.prompt("Patch cycle code (example: Q4-2026)");
    if(!value?.trim())return;
    try{
      const created=await createInventoryPatchCycle(value.trim(),token);
      const rows=await getInventoryPatchCycles(token);setCycles(rows);setCycleId(created.id);
      setNotice({variant:"success",message:`${created.code} patch cycle is ready.`});
    }catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to create patch cycle"});}
  }

  function beginAdd(){
    setEditingAsset(null);setAssetForm(emptyAsset);setActivityForm(emptyActivity);setFormOpen(true);
  }

  function beginEdit(item:InventoryPatchingAsset){
    setEditingAsset(item);
    setAssetForm({
      asset_identifier:item.asset_identifier,
      hostname:item.hostname,
      application:item.application,
      application_owner:item.application_owner,
      asset_type:item.asset_type,
      environment_name:item.environment_name,
      environment_class:item.environment_class,
    });
    setActivityForm({
      previous_patched_date:item.activity?.previous_patched_date||"",
      planned_date:item.activity?.planned_date||"",
      status:item.activity?.status||"NOT_STARTED",
      app_team_approval:item.activity?.app_team_approval||"",
      cr_number:item.activity?.cr_number||"",
      comments:item.activity?.comments||"",
      patch_role:item.activity?.patch_role||"",
    });
    setDetail(null);setFormOpen(true);
  }

  async function saveAsset(event:FormEvent){
    event.preventDefault();
    if(!cycleId){setNotice({variant:"error",message:"Create or select a patch cycle first."});return;}
    setSaving(true);setNotice(null);
    try{
      let saved:InventoryPatchingAsset;
      if(editingAsset){
        saved=editingAsset.source_type==="GTB"
          ?editingAsset
          :await updateInventoryPatchingAsset(editingAsset.id,assetForm,token);
      }else{
        saved=await createInventoryPatchingAsset(assetForm,token);
      }
      await saveInventoryPatchActivity(saved.id,cycleId,{
        ...activityForm,
        previous_patched_date:activityForm.previous_patched_date||null,
        planned_date:activityForm.planned_date||null,
      },token);
      setFormOpen(false);setEditingAsset(null);
      setNotice({variant:"success",message:`${saved.asset_identifier} patching details saved for ${currentCycle?.code||"selected cycle"}.`});
      await loadData();
    }catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to save patching asset"});}
    finally{setSaving(false);}
  }

  async function removeAsset(item:InventoryPatchingAsset){
    if(item.source_type==="GTB"){setNotice({variant:"info",message:"This asset is linked to GTB Inventory and remains visible while the GTB record is active."});return;}
    if(!window.confirm(`Remove ${item.asset_identifier} from Patching inventory?`))return;
    try{await deleteInventoryPatchingAsset(item.id,token);setDetail(null);setNotice({variant:"success",message:"Patching asset removed."});await loadData();}
    catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to remove patching asset"});}
  }

  function beginImport(){setImportOpen(true);setImportFile(null);setImportPreview(null);setNotice(null);}

  async function previewImport(event:FormEvent){
    event.preventDefault();if(!importFile)return;setImportBusy(true);
    try{setImportPreview(await previewInventoryPatchingExcel(importFile,token));}
    catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to preview patching workbook"});}
    finally{setImportBusy(false);}
  }

  async function commitImport(){
    if(!importFile||!importPreview)return;setImportBusy(true);
    try{
      const result=await commitInventoryPatchingExcel(importFile,token);
      setImportOpen(false);setImportFile(null);setImportPreview(null);
      const rows=await getInventoryPatchCycles(token);setCycles(rows);
      const importedCycle=rows.find(item=>item.code===result.cycle_code);if(importedCycle)setCycleId(importedCycle.id);
      setNotice({variant:"success",message:`${result.cycle_code}: ${result.created_assets} new assets, ${result.updated_assets} matched assets, ${result.updated_activities} patch activities loaded.`});
      await loadData(importedCycle?.id||cycleId);
    }catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to import patching tracker"});}
    finally{setImportBusy(false);}
  }

  async function runExport(format:"xlsx"|"pdf"){
    setExportBusy(format);
    try{await downloadInventoryExport("patching",format,token,{cycle_id:cycleId||undefined,environment_class:environmentClass||undefined,status:status||undefined});}
    catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to export patching inventory"});}
    finally{setExportBusy(null);}
  }

  const envCounts=summary?.environment_counts||{NON_PROD:0,PROD:0,DR:0};
  const statusCounts=summary?.status_counts||{NOT_STARTED:0,SCHEDULED:0,IN_PROGRESS:0,COMPLETED:0,BLOCKED:0};

  return <div className="patching-inventory">
    {notice&&<div className={`inventory-notice ${notice.variant}`}>{notice.message}</div>}

    <section className="inventory-section-bar patching-heading">
      <div>
        <button className="inventory-back" onClick={onBack}><ArrowLeft size={16}/>Inventory</button>
        <span className="eyebrow">PATCH MANAGEMENT</span>
        <h2>Patching Inventory</h2>
        <p>Server and cluster patch scope, approvals, CR tracking and quarter-by-quarter patch history.</p>
      </div>
      <div className="inventory-section-actions">
        <button className="secondary-button" disabled={!!exportBusy} onClick={()=>void runExport("xlsx")}><Download size={15}/>{exportBusy==="xlsx"?"Exporting...":"Excel"}</button>
        <button className="secondary-button" disabled={!!exportBusy} onClick={()=>void runExport("pdf")}><FileText size={15}/>{exportBusy==="pdf"?"Exporting...":"PDF"}</button>
        <button className="secondary-button" onClick={beginImport}><FileSpreadsheet size={15}/>Import tracker</button>
        <button className="secondary-button" onClick={()=>void createCycle()}><CalendarDays size={15}/>New cycle</button>
        <button className="primary-button" onClick={beginAdd}><Plus size={15}/>Add asset</button>
      </div>
    </section>

    <section className="patch-cycle-bar">
      <label><span>Patch cycle</span><select value={cycleId} onChange={e=>setCycleId(Number(e.target.value))}>{cycles.map(item=><option key={item.id} value={item.id}>{item.code}</option>)}</select></label>
      <div className="patch-cycle-context"><CalendarDays size={17}/><div><strong>{currentCycle?.code||"No cycle"}</strong><span>Historical activities are retained per cycle.</span></div></div>
    </section>

    <section className="patch-summary-grid">
      <button className={!environmentClass?"active":""} onClick={()=>setEnvironmentClass("")}><span>Total assets</span><strong>{summary?.total_assets??0}</strong><small>All patching scope</small></button>
      <button className={environmentClass==="NON_PROD"?"active":""} onClick={()=>setEnvironmentClass("NON_PROD")}><span>Non-Prod</span><strong>{envCounts.NON_PROD}</strong><small>Development & testing</small></button>
      <button className={environmentClass==="PROD"?"active critical":""} onClick={()=>setEnvironmentClass("PROD")}><span>Production</span><strong>{envCounts.PROD}</strong><small>Critical production</small></button>
      <button className={environmentClass==="DR"?"active":""} onClick={()=>setEnvironmentClass("DR")}><span>DR</span><strong>{envCounts.DR}</strong><small>Disaster recovery</small></button>
    </section>

    <section className="patch-status-grid">
      {(["COMPLETED","SCHEDULED","IN_PROGRESS","BLOCKED","NOT_STARTED"] as InventoryPatchStatus[]).map(item=><button key={item} className={`patch-status-card ${item.toLowerCase()} ${status===item?"active":""}`} onClick={()=>setStatus(current=>current===item?"":item)}>
        {item==="COMPLETED"?<CheckCircle2 size={17}/>:item==="BLOCKED"?<ShieldAlert size={17}/>:<Clock3 size={17}/>}
        <div><strong>{statusCounts[item]||0}</strong><span>{STATUS_LABELS[item]}</span></div>
      </button>)}
    </section>

    <section className="inventory-record-panel">
      <div className="inventory-record-toolbar patch-toolbar">
        <div className="inventory-search"><Search size={17}/><input value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=>{if(e.key==="Enter")void loadData();}} placeholder="Search IP, cluster, hostname, application, owner, CR or comments..."/></div>
        <button className="secondary-button" disabled={loading} onClick={()=>void loadData()}><RefreshCw size={15} className={loading?"spin":""}/>Refresh</button>
        <span>{filtered.length} shown</span>
      </div>
      <div className="inventory-table-wrap patch-table-wrap"><table className="inventory-table patch-table">
        <thead><tr><th>IP / Cluster</th><th>Hostname</th><th>Application</th><th>Class</th><th>Type</th><th>Previous Patch</th><th>Planned</th><th>Status</th><th>Approval</th><th>CR</th><th>Source</th><th/></tr></thead>
        <tbody>
          {filtered.map(item=>{const activity=item.activity;return <tr key={item.id} className={item.environment_class==="PROD"?"patch-prod-row":""}>
            <td><strong>{item.asset_identifier}</strong></td><td>{item.hostname||"—"}</td><td>{item.application||"—"}{item.application_owner&&<small className="patch-owner">{item.application_owner}</small>}</td>
            <td><span className={`patch-env ${item.environment_class.toLowerCase()}`}>{classLabel(item.environment_class)}</span></td><td>{item.asset_type||"—"}</td>
            <td>{dateText(activity?.previous_patched_date)}</td><td>{dateText(activity?.planned_date)}</td>
            <td><span className={`patch-status ${(activity?.status||"NOT_STARTED").toLowerCase()}`}>{STATUS_LABELS[activity?.status||"NOT_STARTED"]}</span></td>
            <td>{activity?.app_team_approval||"—"}</td><td><strong>{activity?.cr_number||"—"}</strong></td><td><span className={`patch-source ${item.source_type.toLowerCase()}`}>{item.source_type}</span></td>
            <td><button className="inventory-row-action" onClick={()=>setDetail(item)}>View</button></td>
          </tr>})}
          {!loading&&filtered.length===0&&<tr><td colSpan={12}><div className="inventory-empty">No patching assets match this cycle and filter selection.</div></td></tr>}
        </tbody>
      </table></div>
    </section>

    {detail&&<div className="inventory-modal-backdrop" onMouseDown={()=>setDetail(null)}><article className="inventory-modal inventory-detail patch-detail" onMouseDown={e=>e.stopPropagation()}>
      <button className="inventory-modal-close" onClick={()=>setDetail(null)}><X size={18}/></button>
      <div className="inventory-modal-heading"><div className="inventory-card-icon"><Server size={21}/></div><div><span className="eyebrow">{detail.environment_class} · {detail.source_type}</span><h2>{detail.hostname||detail.asset_identifier}</h2><p>{detail.application||"Patching asset"} · {detail.asset_identifier}</p></div></div>
      <div className="inventory-detail-grid"><div><span>IP / Cluster</span><strong>{detail.asset_identifier}</strong></div><div><span>Hostname</span><strong>{detail.hostname||"—"}</strong></div><div><span>Application</span><strong>{detail.application||"—"}</strong></div><div><span>Owner</span><strong>{detail.application_owner||"—"}</strong></div><div><span>Type</span><strong>{detail.asset_type||"—"}</strong></div><div><span>Source</span><strong>{detail.source_type}</strong></div></div>
      <section className="patch-activity-detail"><h3>{detail.activity?.cycle_code||currentCycle?.code} activity</h3><div className="inventory-detail-grid"><div><span>Previous patch</span><strong>{dateText(detail.activity?.previous_patched_date)}</strong></div><div><span>Planned date</span><strong>{dateText(detail.activity?.planned_date)}</strong></div><div><span>Status</span><strong>{STATUS_LABELS[detail.activity?.status||"NOT_STARTED"]}</strong></div><div><span>Approval</span><strong>{detail.activity?.app_team_approval||"—"}</strong></div><div><span>CR Number</span><strong>{detail.activity?.cr_number||"—"}</strong></div><div><span>Role</span><strong>{detail.activity?.patch_role||"—"}</strong></div></div><div className="inventory-detail-block"><span>Comments</span><p>{detail.activity?.comments||"—"}</p></div></section>
      <div className="inventory-modal-footer">{detail.source_type!=="GTB"&&<button className="danger-button" onClick={()=>void removeAsset(detail)}><Trash2 size={14}/>Remove</button>}<button className="primary-button" onClick={()=>beginEdit(detail)}><Pencil size={14}/>Update patching</button></div>
    </article></div>}

    {formOpen&&<div className="inventory-modal-backdrop" onMouseDown={()=>!saving&&setFormOpen(false)}><form className="inventory-modal patch-form" onSubmit={saveAsset} onMouseDown={e=>e.stopPropagation()}>
      <button type="button" className="inventory-modal-close" onClick={()=>setFormOpen(false)}><X size={18}/></button>
      <span className="eyebrow">{editingAsset?"PATCH ACTIVITY":"NEW PATCHING ASSET"}</span><h2>{editingAsset?editingAsset.hostname||editingAsset.asset_identifier:"Add patching asset"}</h2>
      {editingAsset?.source_type==="GTB"&&<div className="inventory-import-security"><CheckCircle2 size={17}/><div><strong>Linked to GTB Inventory</strong><span>Server identity fields are maintained from GTB. Update the patch activity below.</span></div></div>}
      <div className="inventory-form-grid">
        <div className="inventory-form-divider"><Server size={15}/>Asset</div>
        <label>IP / Cluster Name<input disabled={editingAsset?.source_type==="GTB"} value={assetForm.asset_identifier} onChange={e=>setAssetForm(v=>({...v,asset_identifier:e.target.value}))}/></label>
        <label>Hostname<input disabled={editingAsset?.source_type==="GTB"} value={assetForm.hostname} onChange={e=>setAssetForm(v=>({...v,hostname:e.target.value}))}/></label>
        <label>Application<input disabled={editingAsset?.source_type==="GTB"} value={assetForm.application} onChange={e=>setAssetForm(v=>({...v,application:e.target.value}))}/></label>
        <label>Application Owner<input value={assetForm.application_owner} onChange={e=>setAssetForm(v=>({...v,application_owner:e.target.value}))}/></label>
        <label>Type<input disabled={editingAsset?.source_type==="GTB"} value={assetForm.asset_type} onChange={e=>setAssetForm(v=>({...v,asset_type:e.target.value}))} placeholder="APP SERVER / SQL Database / AKS"/></label>
        <label>Environment / source env<input disabled={editingAsset?.source_type==="GTB"} value={assetForm.environment_name} onChange={e=>setAssetForm(v=>({...v,environment_name:e.target.value}))}/></label>
        <label>Patching class<select disabled={editingAsset?.source_type==="GTB"} value={assetForm.environment_class} onChange={e=>setAssetForm(v=>({...v,environment_class:e.target.value as InventoryPatchEnvironmentClass}))}><option value="NON_PROD">NON-PROD</option><option value="PROD">PROD</option><option value="DR">DR</option></select></label>
        <div className="inventory-form-divider"><CalendarDays size={15}/>{currentCycle?.code||"Patch cycle"}</div>
        <label>Previous Patched Date<input type="date" value={activityForm.previous_patched_date||""} onChange={e=>setActivityForm(v=>({...v,previous_patched_date:e.target.value}))}/></label>
        <label>Planned Date<input type="date" value={activityForm.planned_date||""} onChange={e=>setActivityForm(v=>({...v,planned_date:e.target.value}))}/></label>
        <label>Status<select value={activityForm.status} onChange={e=>setActivityForm(v=>({...v,status:e.target.value as InventoryPatchStatus}))}>{Object.entries(STATUS_LABELS).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <label>App Team Approval<input value={activityForm.app_team_approval} onChange={e=>setActivityForm(v=>({...v,app_team_approval:e.target.value}))} placeholder="Approved / Pending / ..."/></label>
        <label>CR Number<input value={activityForm.cr_number} onChange={e=>setActivityForm(v=>({...v,cr_number:e.target.value}))} placeholder="CRQ000000..."/></label>
        <label>Patch Role<input value={activityForm.patch_role} onChange={e=>setActivityForm(v=>({...v,patch_role:e.target.value}))} placeholder="Primary / Secondary / DR"/></label>
        <label className="full-width">Comments<textarea rows={4} value={activityForm.comments} onChange={e=>setActivityForm(v=>({...v,comments:e.target.value}))}/></label>
      </div>
      <div className="inventory-modal-footer"><button type="button" className="secondary-button" onClick={()=>setFormOpen(false)}>Cancel</button><button className="primary-button" disabled={saving}>{saving?"Saving...":"Save patching details"}</button></div>
    </form></div>}

    {importOpen&&<div className="inventory-modal-backdrop" onMouseDown={()=>!importBusy&&setImportOpen(false)}><form className="inventory-modal inventory-import-modal" onSubmit={previewImport} onMouseDown={e=>e.stopPropagation()}>
      <button type="button" className="inventory-modal-close" onClick={()=>setImportOpen(false)}><X size={18}/></button>
      <div className="inventory-modal-heading"><div className="inventory-card-icon"><FileSpreadsheet size={21}/></div><div><span className="eyebrow">PATCHING TRACKER IMPORT</span><h2>Import quarterly patching tracker</h2><p>The importer detects Qx-YYYY plus NON-PROD, PROD and DR sections from your existing workbook layout.</p></div></div>
      <label className="inventory-import-drop"><FileSpreadsheet size={30}/><strong>{importFile?importFile.name:"Choose your .xlsx patching tracker"}</strong><span>{importFile?`${(importFile.size/1024/1024).toFixed(2)} MB`:"Maximum 15 MB"}</span><input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={e=>{setImportFile(e.target.files?.[0]||null);setImportPreview(null);}}/></label>
      {importPreview&&<>
        <div className="inventory-import-stats"><div><strong>{importPreview.total_rows}</strong><span>Total assets</span></div><div><strong>{importPreview.environment_counts.NON_PROD||0}</strong><span>Non-Prod</span></div><div><strong>{importPreview.environment_counts.PROD||0}</strong><span>Prod</span></div><div><strong>{importPreview.environment_counts.DR||0}</strong><span>DR</span></div><div><strong>{importPreview.cycle_code}</strong><span>Cycle</span></div><div className={importPreview.warning_count?"warning":""}><strong>{importPreview.warning_count}</strong><span>Warnings</span></div></div>
        {importPreview.warnings.length>0&&<div className="inventory-import-warnings"><div className="inventory-import-warning-title"><AlertTriangle size={16}/>Review warnings</div><div className="inventory-import-warning-list">{importPreview.warnings.slice(0,20).map((w,i)=><p key={i}>{w}</p>)}</div></div>}
        <div className="inventory-import-preview-table"><table className="inventory-table"><thead><tr><th>Row</th><th>Class</th><th>IP / Cluster</th><th>Hostname</th><th>Application</th><th>Owner</th><th>Type</th><th>Previous</th><th>Planned</th><th>Status</th><th>CR</th></tr></thead><tbody>{importPreview.preview_rows.map(row=><tr key={row.source_row}><td>{row.source_row}</td><td><span className={`patch-env ${row.environment_class.toLowerCase()}`}>{classLabel(row.environment_class)}</span></td><td>{row.asset_identifier||"—"}</td><td>{row.hostname||"—"}</td><td>{row.application||"—"}</td><td>{row.application_owner||"—"}</td><td>{row.asset_type||"—"}</td><td>{row.previous_patched_date||"—"}</td><td>{row.planned_date||"—"}</td><td>{row.status||"Not Started"}</td><td>{row.cr_number||"—"}</td></tr>)}</tbody></table></div>
      </>}
      <div className="inventory-modal-footer"><button type="button" className="secondary-button" disabled={importBusy} onClick={()=>setImportOpen(false)}>Cancel</button>{!importPreview?<button className="primary-button" disabled={!importFile||importBusy}>{importBusy?"Reading tracker...":"Preview import"}</button>:<><button type="button" className="secondary-button" disabled={importBusy} onClick={()=>setImportPreview(null)}>Choose another file</button><button type="button" className="primary-button" disabled={importBusy} onClick={()=>void commitImport()}>{importBusy?"Importing...":`Import ${importPreview.cycle_code}`}</button></>}</div>
    </form></div>}
  </div>;
}
