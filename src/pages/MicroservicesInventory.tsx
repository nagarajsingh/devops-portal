import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Database,
  Download,
  Eye,
  EyeOff,
  FileSpreadsheet,
  FileText,
  History,
  Layers3,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import {
  commitInventoryMsExcel,
  createInventoryEnvironment,
  createInventoryMsConfiguration,
  createInventoryMsGroup,
  createInventoryMsService,
  deleteInventoryMsConfiguration,
  downloadInventoryExport,
  getInventoryEnvironments,
  getInventoryMsConfigurations,
  getInventoryMsGroups,
  getInventoryMsServices,
  previewInventoryMsExcel,
  revealInventoryMsPassword,
  updateInventoryMsConfiguration,
  type InventoryMsConfigurationInput,
} from "../services/api";
import InventoryHistoryModal from "../components/InventoryHistoryModal";
import type {
  InventoryEnvironment,
  InventoryMsConfiguration,
  InventoryMsGroup,
  InventoryMsImportPreview,
  InventoryMsService,
} from "../types";

type Notice = { variant: "success" | "error" | "info"; message: string };

type Props = {
  token:string;
  environments:InventoryEnvironment[];
  onBack:()=>void;
  onEnvironmentsChange:(rows:InventoryEnvironment[])=>void;
};

const emptyConfig=(serviceId=0,environmentId=0):InventoryMsConfigurationInput=>({
  service_id:serviceId,
  environment_id:environmentId,
  connection_name:"PRIMARY",
  db_url:"",
  db_name:"",
  db_username:"",
  db_password:"",
  notes:"",
});

function formatDate(value?:string){
  if(!value)return "—";
  const date=new Date(value);
  return Number.isNaN(date.getTime())?value:date.toLocaleString();
}

export default function MicroservicesInventory({token,environments,onBack,onEnvironmentsChange}:Props){
  const [groups,setGroups]=useState<InventoryMsGroup[]>([]);
  const [selectedGroup,setSelectedGroup]=useState<InventoryMsGroup|null>(null);
  const [services,setServices]=useState<InventoryMsService[]>([]);
  const [selectedService,setSelectedService]=useState<InventoryMsService|null>(null);
  const [configurations,setConfigurations]=useState<InventoryMsConfiguration[]>([]);
  const [environmentId,setEnvironmentId]=useState(0);
  const [search,setSearch]=useState("");
  const [loading,setLoading]=useState(true);
  const [notice,setNotice]=useState<Notice|null>(null);

  const [catalogMode,setCatalogMode]=useState<"group"|"service"|"environment"|null>(null);
  const [catalogCode,setCatalogCode]=useState("");
  const [catalogName,setCatalogName]=useState("");
  const [catalogBusy,setCatalogBusy]=useState(false);

  const [configOpen,setConfigOpen]=useState(false);
  const [editingConfigId,setEditingConfigId]=useState<number|null>(null);
  const [configForm,setConfigForm]=useState<InventoryMsConfigurationInput>(emptyConfig());
  const [configBusy,setConfigBusy]=useState(false);

  const [detail,setDetail]=useState<InventoryMsConfiguration|null>(null);
  const [historyDetail,setHistoryDetail]=useState<InventoryMsConfiguration|null>(null);
  const [revealedPassword,setRevealedPassword]=useState("");
  const [revealBusy,setRevealBusy]=useState(false);
  const [tablePasswords,setTablePasswords]=useState<Record<number,string>>({});
  const [tableRevealBusy,setTableRevealBusy]=useState<number|null>(null);

  const [importOpen,setImportOpen]=useState(false);
  const [importFile,setImportFile]=useState<File|null>(null);
  const [importPreview,setImportPreview]=useState<InventoryMsImportPreview|null>(null);
  const [importBusy,setImportBusy]=useState(false);
  const [exportBusy,setExportBusy]=useState<"xlsx"|"pdf"|null>(null);

  async function loadGroups(){
    setLoading(true);
    try{setGroups(await getInventoryMsGroups(token));}
    catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to load Microservices groups"});}
    finally{setLoading(false);}
  }

  useEffect(()=>{void loadGroups();},[token]);

  async function openGroup(group:InventoryMsGroup){
    setSelectedGroup(group);
    setSelectedService(null);
    setConfigurations([]);
    setTablePasswords({});
    setEnvironmentId(0);
    setSearch("");
    setLoading(true);
    try{setServices(await getInventoryMsServices(token,group.id));}
    catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to load services"});}
    finally{setLoading(false);}
  }

  async function openService(service:InventoryMsService){
    setSelectedService(service);
    setEnvironmentId(0);
    setSearch("");
    setTablePasswords({});
    setLoading(true);
    try{setConfigurations(await getInventoryMsConfigurations(token,{service_id:service.id}));}
    catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to load service configurations"});}
    finally{setLoading(false);}
  }

  async function refreshCurrent(){
    await loadGroups();
    if(selectedGroup){
      const nextServices=await getInventoryMsServices(token,selectedGroup.id);
      setServices(nextServices);
      const refreshedGroup=(await getInventoryMsGroups(token)).find(item=>item.id===selectedGroup.id);
      if(refreshedGroup)setSelectedGroup(refreshedGroup);
      if(selectedService){
        const refreshedService=nextServices.find(item=>item.id===selectedService.id);
        if(refreshedService)setSelectedService(refreshedService);
        setConfigurations(await getInventoryMsConfigurations(token,{service_id:selectedService.id}));
      }
    }
  }

  const envCounts=useMemo(()=>{
    const counts=new Map<number,number>();
    configurations.forEach(item=>counts.set(item.environment_id,(counts.get(item.environment_id)||0)+1));
    return counts;
  },[configurations]);

  const filteredConfigs=useMemo(()=>{
    const needle=search.trim().toLowerCase();
    return configurations.filter(item=>{
      if(environmentId&&item.environment_id!==environmentId)return false;
      if(!needle)return true;
      return [item.connection_name,item.db_url,item.db_name,item.db_username,item.notes].some(value=>value.toLowerCase().includes(needle));
    });
  },[configurations,environmentId,search]);

  async function saveCatalog(event:FormEvent){
    event.preventDefault();
    if(!catalogMode||!catalogCode.trim())return;
    setCatalogBusy(true);
    setNotice(null);
    try{
      if(catalogMode==="group"){
        await createInventoryMsGroup({code:catalogCode.trim(),display_name:catalogName.trim()||catalogCode.trim()},token);
        setNotice({variant:"success",message:`${catalogName.trim()||catalogCode.trim()} group added.`});
        await loadGroups();
      }else if(catalogMode==="service"){
        if(!selectedGroup)throw new Error("Select a group first");
        await createInventoryMsService({group_id:selectedGroup.id,code:catalogCode.trim(),display_name:catalogName.trim()||catalogCode.trim()},token);
        setServices(await getInventoryMsServices(token,selectedGroup.id));
        setNotice({variant:"success",message:`${catalogName.trim()||catalogCode.trim()} service added to ${selectedGroup.display_name}.`});
      }else{
        await createInventoryEnvironment({category:"MICROSERVICES",code:catalogCode.trim(),display_name:catalogName.trim()||catalogCode.trim()},token);
        onEnvironmentsChange(await getInventoryEnvironments(token,"MICROSERVICES"));
        setNotice({variant:"success",message:`${catalogName.trim()||catalogCode.trim()} environment added.`});
      }
      setCatalogMode(null);setCatalogCode("");setCatalogName("");
    }catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to add inventory catalog item"});}
    finally{setCatalogBusy(false);}
  }

  function beginCreateConfig(){
    if(!selectedService)return;
    setEditingConfigId(null);
    setConfigForm(emptyConfig(selectedService.id,environmentId||environments[0]?.id||0));
    setConfigOpen(true);
  }

  function beginEditConfig(item:InventoryMsConfiguration){
    setEditingConfigId(item.id);
    setConfigForm({
      service_id:item.service_id,
      environment_id:item.environment_id,
      connection_name:item.connection_name,
      db_url:item.db_url,
      db_name:item.db_name,
      db_username:item.db_username,
      db_password:"",
      notes:item.notes,
    });
    setDetail(null);setRevealedPassword("");setConfigOpen(true);
  }

  async function saveConfig(event:FormEvent){
    event.preventDefault();
    setConfigBusy(true);setNotice(null);
    try{
      const payload={...configForm,db_password:configForm.db_password||undefined};
      const saved=editingConfigId
        ?await updateInventoryMsConfiguration(editingConfigId,payload,token)
        :await createInventoryMsConfiguration(payload,token);
      setConfigOpen(false);setEditingConfigId(null);
      setNotice({variant:"success",message:`${saved.service_name} / ${saved.environment_name} / ${saved.connection_name} / ${saved.db_name||"DB"} saved.`});
      await refreshCurrent();
    }catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to save database configuration"});}
    finally{setConfigBusy(false);}
  }

  async function removeConfig(item:InventoryMsConfiguration){
    if(!window.confirm(`Remove ${item.service_name} / ${item.environment_name} / ${item.connection_name} / ${item.db_name||"DB"}?`))return;
    try{
      await deleteInventoryMsConfiguration(item.id,token);
      setDetail(null);setRevealedPassword("");
      setNotice({variant:"success",message:"Database configuration removed."});
      await refreshCurrent();
    }catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to remove configuration"});}
  }

  async function revealPassword(){
    if(!detail)return;
    if(revealedPassword){setRevealedPassword("");return;}
    setRevealBusy(true);
    try{
      const result=await revealInventoryMsPassword(detail.id,token);
      setRevealedPassword(result.password);
      window.setTimeout(()=>setRevealedPassword(""),30000);
    }catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to reveal database password"});}
    finally{setRevealBusy(false);}
  }

  async function toggleTablePassword(item:InventoryMsConfiguration){
    if(tablePasswords[item.id]){
      setTablePasswords(current=>{
        const next={...current};
        delete next[item.id];
        return next;
      });
      return;
    }
    if(!item.db_password_configured)return;
    setTableRevealBusy(item.id);
    try{
      const result=await revealInventoryMsPassword(item.id,token);
      setTablePasswords(current=>({...current,[item.id]:result.password}));
      window.setTimeout(()=>{
        setTablePasswords(current=>{
          if(!current[item.id])return current;
          const next={...current};
          delete next[item.id];
          return next;
        });
      },30000);
    }catch(error){
      setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to reveal database password"});
    }finally{
      setTableRevealBusy(current=>current===item.id?null:current);
    }
  }

  function beginImport(){
    setImportOpen(true);setImportFile(null);setImportPreview(null);setNotice(null);
  }

  async function previewImport(event:FormEvent){
    event.preventDefault();
    if(!importFile)return;
    setImportBusy(true);
    try{setImportPreview(await previewInventoryMsExcel(importFile,token));}
    catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to preview Microservices Excel import"});}
    finally{setImportBusy(false);}
  }

  async function commitImport(){
    if(!importFile||!importPreview)return;
    setImportBusy(true);
    try{
      const result=await commitInventoryMsExcel(importFile,token);
      setImportOpen(false);setImportFile(null);setImportPreview(null);
      onEnvironmentsChange(await getInventoryEnvironments(token,"MICROSERVICES"));
      await refreshCurrent();
      setNotice({variant:"success",message:`Excel import completed: ${result.created_count} created, ${result.updated_count} updated, ${result.skipped_count} skipped.`});
    }catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to import Microservices inventory"});}
    finally{setImportBusy(false);}
  }

  async function runExport(format:"xlsx"|"pdf"){
    setExportBusy(format);
    try{
      await downloadInventoryExport("microservices",format,token,{
        group_id:selectedGroup?.id,
        service_id:selectedService?.id,
        environment_id:environmentId||undefined,
      });
    }catch(error){setNotice({variant:"error",message:error instanceof Error?error.message:"Unable to export Microservices inventory"});}
    finally{setExportBusy(null);}
  }

  function back(){
    if(selectedService){setSelectedService(null);setConfigurations([]);setTablePasswords({});setEnvironmentId(0);setSearch("");return;}
    if(selectedGroup){setSelectedGroup(null);setServices([]);return;}
    onBack();
  }

  return <div className="ms-inventory">
    {notice&&<div className={`inventory-notice ${notice.variant}`}>{notice.message}</div>}

    <section className="inventory-section-bar">
      <div>
        <button className="inventory-back" onClick={back}><ArrowLeft size={16}/>{selectedService?selectedGroup?.display_name:selectedGroup?"Microservices":"Inventory"}</button>
        <span className="eyebrow">MICROSERVICES INVENTORY</span>
        <h2>{selectedService?.display_name||selectedGroup?.display_name||"Groups"}</h2>
        <p>{selectedService?"Environment-specific database connections and encrypted credentials.":selectedGroup?"Services within this operational group.":"Manage API Banking, H2H, Collections, Native Mobile, Safenet and future groups."}</p>
      </div>
      <div className="inventory-section-actions">
        <button className="secondary-button" disabled={!!exportBusy} onClick={()=>void runExport("xlsx")}><Download size={15}/>{exportBusy==="xlsx"?"Exporting...":"Excel"}</button>
        <button className="secondary-button" disabled={!!exportBusy} onClick={()=>void runExport("pdf")}><FileText size={15}/>{exportBusy==="pdf"?"Exporting...":"PDF"}</button>
        {!selectedGroup&&<button className="secondary-button" onClick={beginImport}><FileSpreadsheet size={15}/>Import Excel</button>}
        <button className="secondary-button" onClick={()=>{setCatalogMode("environment");setCatalogCode("");setCatalogName("");}}><Layers3 size={15}/>Add Microservices environment</button>
        {!selectedGroup&&<button className="primary-button" onClick={()=>{setCatalogMode("group");setCatalogCode("");setCatalogName("");}}><Plus size={15}/>Add group</button>}
        {selectedGroup&&!selectedService&&<button className="primary-button" onClick={()=>{setCatalogMode("service");setCatalogCode("");setCatalogName("");}}><Plus size={15}/>Add service</button>}
        {selectedService&&<button className="primary-button" onClick={beginCreateConfig}><Plus size={15}/>Add DB configuration</button>}
      </div>
    </section>

    {loading&&<div className="inventory-loading">Loading Microservices inventory...</div>}

    {!loading&&!selectedGroup&&<section className="ms-group-grid">
      {groups.map(group=><button key={group.id} className="inventory-category-card ms-group-card" onClick={()=>void openGroup(group)}>
        <div className="inventory-card-icon"><Database size={24}/></div>
        <div className="inventory-category-copy"><span className="eyebrow">{group.code}</span><h2>{group.display_name}</h2><p>{group.service_count} services · {group.environment_count} environments</p></div>
        <div className="inventory-card-stats"><span><strong>{group.service_count}</strong> Services</span><span><strong>{group.configuration_count}</strong> DB configs</span><span><strong>{group.environment_count}</strong> Envs</span></div>
      </button>)}
    </section>}

    {!loading&&selectedGroup&&!selectedService&&<>
      <div className="inventory-search ms-service-search"><Search size={17}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search services..."/></div>
      <section className="inventory-application-grid">
        {services.filter(item=>!search.trim()||[item.code,item.display_name].some(v=>v.toLowerCase().includes(search.toLowerCase()))).map(service=><button className="inventory-application-card" key={service.id} onClick={()=>void openService(service)}>
          <div className="inventory-application-top"><div className="inventory-card-icon small"><Server size={20}/></div><span>{service.group_code}</span></div>
          <h3>{service.display_name}</h3><p>{service.code}</p>
          <div className="inventory-application-stats"><span><strong>{service.configuration_count}</strong> DB configs</span><span><strong>{service.environment_count}</strong> environments</span></div>
        </button>)}
      </section>
    </>}

    {!loading&&selectedService&&<>
      <section className="inventory-environment-strip">
        <button className={environmentId===0?"active":""} onClick={()=>setEnvironmentId(0)}><strong>All</strong><span>{configurations.length}</span></button>
        {environments.map(env=><button key={env.id} className={environmentId===env.id?"active":""} onClick={()=>setEnvironmentId(env.id)}><strong>{env.display_name}</strong><span>{envCounts.get(env.id)||0}</span></button>)}
      </section>
      <section className="inventory-record-panel">
        <div className="inventory-record-toolbar"><div className="inventory-search"><Search size={17}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search connection, DB URL, name, username or notes..."/></div><span>{filteredConfigs.length} shown</span></div>
        <div className="inventory-table-wrap"><table className="inventory-table ms-config-table">
          <thead><tr><th>Environment</th><th>Connection</th><th>DB URL</th><th>DB Name</th><th>DB Username</th><th>Password</th><th>Updated</th><th/></tr></thead>
          <tbody>
            {filteredConfigs.map(item=><tr key={item.id}>
              <td><span className="inventory-env-badge">{item.environment_name}</span></td><td><strong>{item.connection_name}</strong></td><td>{item.db_url||"—"}</td><td>{item.db_name||"—"}</td><td>{item.db_username||"—"}</td>
              <td><div className="inventory-inline-secret">
  <code>{tablePasswords[item.id]||(item.db_password_configured?"••••••••":"Not configured")}</code>
  {item.db_password_configured&&<button type="button" title={tablePasswords[item.id]?"Hide password":"Reveal password"} aria-label={tablePasswords[item.id]?"Hide password":"Reveal password"} disabled={tableRevealBusy===item.id} onClick={()=>void toggleTablePassword(item)}>
    {tableRevealBusy===item.id?<RefreshCw size={15} className="spin"/>:tablePasswords[item.id]?<EyeOff size={15}/>:<Eye size={15}/>}
  </button>}
</div></td>
              <td><small>{formatDate(item.updated_at)}</small></td>
              <td><button className="inventory-row-action" onClick={()=>{setDetail(item);setRevealedPassword("");}}><Database size={15}/>View</button></td>
            </tr>)}
            {filteredConfigs.length===0&&<tr><td colSpan={8}><div className="inventory-empty">No database configurations for this selection.</div></td></tr>}
          </tbody>
        </table></div>
      </section>
    </>}

    {catalogMode&&<div className="inventory-modal-backdrop" onMouseDown={()=>setCatalogMode(null)}><form className="inventory-modal inventory-catalog-form" onSubmit={saveCatalog} onMouseDown={e=>e.stopPropagation()}>
      <button type="button" className="inventory-modal-close" onClick={()=>setCatalogMode(null)}><X size={18}/></button>
      <span className="eyebrow">MICROSERVICES CATALOG</span><h2>{catalogMode==="environment"?"Add Microservices environment":`Add ${catalogMode}`}</h2><p>New catalog entries are immediately available without a code deployment.</p>
      <label>Code / name<input required autoFocus value={catalogCode} onChange={e=>setCatalogCode(e.target.value)} placeholder={catalogMode==="group"?"Example: PAYMENTS":catalogMode==="service"?"Example: h2h-statement-service":"Example: R2UAT"}/></label>
      <label>Display name <small>(optional)</small><input value={catalogName} onChange={e=>setCatalogName(e.target.value)}/></label>
      <div className="inventory-modal-footer"><button type="button" className="secondary-button" onClick={()=>setCatalogMode(null)}>Cancel</button><button className="primary-button" disabled={catalogBusy}>{catalogBusy?"Adding...":"Add"}</button></div>
    </form></div>}

    {configOpen&&<div className="inventory-modal-backdrop" onMouseDown={()=>!configBusy&&setConfigOpen(false)}><form className="inventory-modal" onSubmit={saveConfig} onMouseDown={e=>e.stopPropagation()}>
      <button type="button" className="inventory-modal-close" onClick={()=>setConfigOpen(false)}><X size={18}/></button>
      <div className="inventory-modal-heading"><div className="inventory-card-icon"><Database size={21}/></div><div><span className="eyebrow">{editingConfigId?"UPDATE DATABASE":"NEW DATABASE"}</span><h2>{selectedService?.display_name}</h2><p>Database credentials are encrypted before storage.</p></div></div>
      <div className="inventory-form-grid">
        <label>Environment<select required value={configForm.environment_id} onChange={e=>setConfigForm(v=>({...v,environment_id:Number(e.target.value)}))}><option value={0}>Select environment</option>{environments.map(env=><option key={env.id} value={env.id}>{env.display_name}</option>)}</select></label>
        <label>Connection name<input required value={configForm.connection_name} onChange={e=>setConfigForm(v=>({...v,connection_name:e.target.value}))} placeholder="PRIMARY"/></label>
        <label className="full-width">DB URL<input value={configForm.db_url} onChange={e=>setConfigForm(v=>({...v,db_url:e.target.value}))} placeholder="jdbc:... or host:port"/></label>
        <label>DB Name<input value={configForm.db_name} onChange={e=>setConfigForm(v=>({...v,db_name:e.target.value}))}/></label>
        <label>DB Username<input value={configForm.db_username} onChange={e=>setConfigForm(v=>({...v,db_username:e.target.value}))}/></label>
        <label className="full-width">DB Password<input type="password" autoComplete="new-password" value={configForm.db_password||""} onChange={e=>setConfigForm(v=>({...v,db_password:e.target.value}))} placeholder={editingConfigId?"Leave blank to keep current password":"Optional"}/></label>
        <label className="full-width">Notes<textarea rows={3} value={configForm.notes} onChange={e=>setConfigForm(v=>({...v,notes:e.target.value}))}/></label>
      </div>
      <div className="inventory-modal-footer"><button type="button" className="secondary-button" onClick={()=>setConfigOpen(false)}>Cancel</button><button className="primary-button" disabled={configBusy||!configForm.environment_id}>{configBusy?"Saving...":"Save configuration"}</button></div>
    </form></div>}

    {detail&&<div className="inventory-modal-backdrop" onMouseDown={()=>{setDetail(null);setRevealedPassword("");}}><article className="inventory-modal inventory-detail" onMouseDown={e=>e.stopPropagation()}>
      <button type="button" className="inventory-modal-close" onClick={()=>{setDetail(null);setRevealedPassword("");}}><X size={18}/></button>
      <div className="inventory-modal-heading"><div className="inventory-card-icon"><Database size={21}/></div><div><span className="eyebrow">{detail.group_name} / {detail.environment_name}</span><h2>{detail.service_name}</h2><p>{detail.connection_name} database connection</p></div></div>
      <div className="inventory-detail-grid"><div><span>Group</span><strong>{detail.group_name}</strong></div><div><span>Service</span><strong>{detail.service_name}</strong></div><div><span>Environment</span><strong>{detail.environment_name}</strong></div><div><span>Connection</span><strong>{detail.connection_name}</strong></div><div><span>DB Name</span><strong>{detail.db_name||"—"}</strong></div><div><span>DB Username</span><strong>{detail.db_username||"—"}</strong></div></div>
      <section className="inventory-detail-block"><span>DB URL</span><pre>{detail.db_url||"—"}</pre></section>
      <section className="inventory-secret-section"><h3><ShieldCheck size={16}/>Database credential</h3><div className="inventory-secret-row"><span>Password</span><code>{revealedPassword||(detail.db_password_configured?"••••••••••••":"Not configured")}</code>{detail.db_password_configured&&<button onClick={()=>void revealPassword()}>{revealedPassword?<EyeOff size={14}/>:<Eye size={14}/>} {revealBusy?"Loading...":revealedPassword?"Hide":"Reveal"}</button>}</div>{revealedPassword&&<small className="inventory-secret-warning">Automatically hidden after 30 seconds. Reveal is audit logged.</small>}</section>
      <section className="inventory-detail-block"><span>Notes</span><p>{detail.notes||"—"}</p></section>
      <div className="inventory-detail-meta"><span>Updated by <strong>{detail.updated_by}</strong></span><span>{formatDate(detail.updated_at)}</span></div>
      <div className="inventory-modal-footer"><button className="secondary-button" onClick={()=>setHistoryDetail(detail)}><History size={14}/>History</button><button className="danger-button" onClick={()=>void removeConfig(detail)}><Trash2 size={14}/>Remove</button><button className="primary-button" onClick={()=>beginEditConfig(detail)}><Pencil size={14}/>Edit</button></div>
    </article></div>}

    {historyDetail&&<InventoryHistoryModal token={token} entityType="MS_CONFIGURATION" entityId={historyDetail.id} entityName={historyDetail.service_name+" / "+historyDetail.environment_name+" / "+historyDetail.connection_name} onClose={()=>setHistoryDetail(null)}/>}

    {importOpen&&<div className="inventory-modal-backdrop" onMouseDown={()=>!importBusy&&setImportOpen(false)}><form className="inventory-modal inventory-import-modal" onSubmit={previewImport} onMouseDown={e=>e.stopPropagation()}>
      <button type="button" className="inventory-modal-close" onClick={()=>setImportOpen(false)}><X size={18}/></button>
      <div className="inventory-modal-heading"><div className="inventory-card-icon"><FileSpreadsheet size={21}/></div><div><span className="eyebrow">MICROSERVICES IMPORT</span><h2>Import Excel inventory</h2><p>Expected columns: GROUP, SERVICE, ENV, CONNECTION NAME, DB URL, DB NAME, DB USERNAME, DB PASSWORD, NOTES. Use one database per row. Multiple rows may use the same service, environment and connection name such as PRIMARY when DB NAME is different.</p></div></div>
      <label className="inventory-import-drop"><FileSpreadsheet size={30}/><strong>{importFile?importFile.name:"Choose an .xlsx workbook"}</strong><span>{importFile?`${(importFile.size/1024/1024).toFixed(2)} MB`:"Maximum 15 MB"}</span><input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={e=>{setImportFile(e.target.files?.[0]||null);setImportPreview(null);}}/></label>
      {!importPreview&&<div className="inventory-import-security"><ShieldCheck size={17}/><div><strong>Secure import</strong><span>Passwords are hidden during preview and encrypted before database storage.</span></div></div>}
      {importPreview&&<>
        <div className="inventory-import-stats"><div><strong>{importPreview.total_rows}</strong><span>Total rows</span></div><div><strong>{importPreview.ready_rows}</strong><span>Ready</span></div><div><strong>{importPreview.group_count}</strong><span>Groups</span></div><div><strong>{importPreview.service_count}</strong><span>Services</span></div><div className={importPreview.invalid_rows?"warning":""}><strong>{importPreview.invalid_rows}</strong><span>Invalid</span></div><div className={importPreview.warning_count?"warning":""}><strong>{importPreview.warning_count}</strong><span>Warnings</span></div></div>
        <div className="inventory-import-summary"><div><CheckCircle2 size={16}/><span>Sheet <strong>{importPreview.sheet_name}</strong></span></div><div><span>Groups</span><p>{importPreview.groups.join(", ")}</p></div><div><span>Environments</span><p>{importPreview.environments.join(", ")}</p></div></div>
        {importPreview.warnings.length>0&&<div className="inventory-import-warnings"><div className="inventory-import-warning-title"><AlertTriangle size={16}/>Review warnings</div><div className="inventory-import-warning-list">{importPreview.warnings.slice(0,20).map((w,i)=><p key={i}>{w}</p>)}</div></div>}
        <div className="inventory-import-preview-table"><table className="inventory-table"><thead><tr><th>Row</th><th>Group</th><th>Service</th><th>Env</th><th>Connection</th><th>DB URL</th><th>DB Name</th><th>User</th><th>Password</th></tr></thead><tbody>{importPreview.preview_rows.map((row,index)=><tr key={`${row.source_row}-${row.source_connection||row.connection_name}-${index}`}><td>{row.source_row}</td><td>{row.group}</td><td><strong>{row.service}</strong></td><td><span className="inventory-env-badge">{row.environment}</span></td><td>{row.connection_name}</td><td>{row.db_url||"—"}</td><td>{row.db_name||"—"}</td><td>{row.db_username||"—"}</td><td><span className={row.db_password_configured?"ms-secret-status configured":"ms-secret-status"}>{row.db_password_configured?"Configured":"No"}</span></td></tr>)}</tbody></table></div>
      </>}
      <div className="inventory-modal-footer"><button type="button" className="secondary-button" disabled={importBusy} onClick={()=>setImportOpen(false)}>Cancel</button>{!importPreview?<button className="primary-button" disabled={!importFile||importBusy}>{importBusy?"Validating...":"Preview import"}</button>:<><button type="button" className="secondary-button" disabled={importBusy} onClick={()=>setImportPreview(null)}>Choose another file</button><button type="button" className="primary-button" disabled={importBusy||!importPreview.ready_rows} onClick={()=>void commitImport()}>{importBusy?"Importing...":`Import ${importPreview.ready_rows} rows`}</button></>}</div>
    </form></div>}
  </div>;
}
