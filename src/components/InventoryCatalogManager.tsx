import { FormEvent, useEffect, useMemo, useState } from "react";
import { Archive, History, Pencil, Plus, RotateCcw, X } from "lucide-react";
import {
  archiveInventoryApplication,
  archiveInventoryEnvironment,
  archiveInventoryMsGroup,
  archiveInventoryMsService,
  createInventoryApplication,
  createInventoryEnvironment,
  createInventoryMsGroup,
  createInventoryMsService,
  getInventoryApplications,
  getInventoryEnvironments,
  getInventoryMsGroups,
  getInventoryMsServices,
  restoreInventoryApplication,
  restoreInventoryEnvironment,
  restoreInventoryMsGroup,
  restoreInventoryMsService,
  updateInventoryApplication,
  updateInventoryEnvironment,
  updateInventoryMsGroup,
  updateInventoryMsService,
} from "../services/api";
import type { InventoryApplication, InventoryEnvironment, InventoryMsGroup, InventoryMsService } from "../types";
import InventoryHistoryModal from "./InventoryHistoryModal";

type Tab="gtb_environment"|"ms_environment"|"application"|"group"|"service";
type EditTarget={kind:Tab;id?:number;code:string;display_name:string;group_id?:number};
type HistoryTarget={type:string;id:number;name:string};

export default function InventoryCatalogManager({token,onClose,onChanged}:{token:string;onClose:()=>void;onChanged?:()=>void}){
  const [tab,setTab]=useState<Tab>("gtb_environment");
  const [gtbEnvironments,setGtbEnvironments]=useState<InventoryEnvironment[]>([]);
  const [msEnvironments,setMsEnvironments]=useState<InventoryEnvironment[]>([]);
  const [applications,setApplications]=useState<InventoryApplication[]>([]);
  const [groups,setGroups]=useState<InventoryMsGroup[]>([]);
  const [services,setServices]=useState<InventoryMsService[]>([]);
  const [editing,setEditing]=useState<EditTarget|null>(null);
  const [history,setHistory]=useState<HistoryTarget|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");

  async function load(){
    const data=await Promise.all([
      getInventoryEnvironments(token,"GTB",true),
      getInventoryEnvironments(token,"MICROSERVICES",true),
      getInventoryApplications("GTB",token,true),
      getInventoryMsGroups(token,true),
      getInventoryMsServices(token,undefined,"",true),
    ]);
    setGtbEnvironments(data[0]);setMsEnvironments(data[1]);setApplications(data[2]);setGroups(data[3]);setServices(data[4]);
  }

  useEffect(()=>{load().catch(e=>setError(e instanceof Error?e.message:"Unable to load inventory catalog"));},[token]);

  const rows=useMemo(()=>{
    if(tab==="gtb_environment")return gtbEnvironments;
    if(tab==="ms_environment")return msEnvironments;
    if(tab==="application")return applications;
    if(tab==="group")return groups;
    return services;
  },[tab,gtbEnvironments,msEnvironments,applications,groups,services]);

  function startAdd(){
    setEditing({kind:tab,code:"",display_name:"",group_id:tab==="service"?(groups.find(g=>g.is_active)?.id||0):undefined});
    setError("");setNotice("");
  }

  function startEdit(row:any){
    setEditing({kind:tab,id:row.id,code:row.code,display_name:row.display_name,group_id:tab==="service"?row.group_id:undefined});
    setError("");setNotice("");
  }

  async function save(e:FormEvent){
    e.preventDefault();
    if(!editing||!editing.code.trim())return;
    setBusy(true);setError("");setNotice("");
    try{
      if(editing.kind==="gtb_environment"||editing.kind==="ms_environment"){
        const category:"GTB"|"MICROSERVICES"=editing.kind==="gtb_environment"?"GTB":"MICROSERVICES";
        const payload={category,code:editing.code,display_name:editing.display_name||editing.code};
        if(editing.id)await updateInventoryEnvironment(editing.id,payload,token);else await createInventoryEnvironment(payload,token);
      }else if(editing.kind==="application"){
        const payload={category:"GTB" as const,code:editing.code,display_name:editing.display_name||editing.code};
        if(editing.id)await updateInventoryApplication(editing.id,payload,token);else await createInventoryApplication(payload,token);
      }else if(editing.kind==="group"){
        const payload={code:editing.code,display_name:editing.display_name||editing.code};
        if(editing.id)await updateInventoryMsGroup(editing.id,payload,token);else await createInventoryMsGroup(payload,token);
      }else{
        if(!editing.group_id)throw new Error("Select a group");
        const payload={group_id:editing.group_id,code:editing.code,display_name:editing.display_name||editing.code};
        if(editing.id)await updateInventoryMsService(editing.id,payload,token);else await createInventoryMsService(payload,token);
      }
      setNotice((editing.id?"Updated":"Added")+" successfully.");
      setEditing(null);
      await load();
      if(onChanged)onChanged();
    }catch(err){setError(err instanceof Error?err.message:"Unable to save catalog item");}
    finally{setBusy(false);}
  }

  async function archive(row:any){
    if(!window.confirm("Remove "+row.display_name+" from active inventory? History will be retained."))return;
    setBusy(true);setError("");setNotice("");
    try{
      if(tab==="gtb_environment")await archiveInventoryEnvironment(row.id,"GTB",token);
      else if(tab==="ms_environment")await archiveInventoryEnvironment(row.id,"MICROSERVICES",token);
      else if(tab==="application")await archiveInventoryApplication(row.id,token);
      else if(tab==="group")await archiveInventoryMsGroup(row.id,token);
      else await archiveInventoryMsService(row.id,token);
      setNotice("Item archived. It can be restored later.");
      await load();
      if(onChanged)onChanged();
    }catch(err){setError(err instanceof Error?err.message:"Unable to archive item");}
    finally{setBusy(false);}
  }

  async function restore(row:any){
    setBusy(true);setError("");setNotice("");
    try{
      if(tab==="gtb_environment")await restoreInventoryEnvironment(row.id,"GTB",token);
      else if(tab==="ms_environment")await restoreInventoryEnvironment(row.id,"MICROSERVICES",token);
      else if(tab==="application")await restoreInventoryApplication(row.id,token);
      else if(tab==="group")await restoreInventoryMsGroup(row.id,token);
      else await restoreInventoryMsService(row.id,token);
      setNotice("Item restored.");
      await load();
      if(onChanged)onChanged();
    }catch(err){setError(err instanceof Error?err.message:"Unable to restore item");}
    finally{setBusy(false);}
  }

  const historyType=tab==="gtb_environment"?"GTB_ENVIRONMENT":tab==="ms_environment"?"MICROSERVICES_ENVIRONMENT":tab==="application"?"APPLICATION":tab==="group"?"MS_GROUP":"MS_SERVICE";

  return <div className="inventory-modal-backdrop" onMouseDown={onClose}>
    <article className="inventory-modal inventory-catalog-manager" onMouseDown={e=>e.stopPropagation()}>
      <button type="button" className="inventory-modal-close" onClick={onClose}><X size={19}/></button>
      <div className="inventory-modal-heading">
        <div>
          <span className="eyebrow">MASTER DATA</span>
          <h2>Manage Inventory Catalog</h2>
          <p>Add, edit, archive and restore environments, applications, groups and services without code changes.</p>
        </div>
      </div>

      <div className="inventory-catalog-tabs">
        {(["gtb_environment","ms_environment","application","group","service"] as Tab[]).map(t=><button type="button" key={t} className={tab===t?"active":""} onClick={()=>{setTab(t);setEditing(null);setError("");setNotice("");}}>
          {t==="gtb_environment"?"GTB Environments":t==="ms_environment"?"Microservices Environments":t==="application"?"GTB Applications":t==="group"?"Microservices Groups":"Microservices Services"}
        </button>)}
      </div>

      {error&&<div className="inventory-notice error">{error}</div>}
      {notice&&<div className="inventory-notice success">{notice}</div>}

      <div className="inventory-catalog-toolbar">
        <span>{rows.length} item{rows.length===1?"":"s"} including archived</span>
        <button type="button" className="primary-button" onClick={startAdd}><Plus size={15}/>Add</button>
      </div>

      <div className="inventory-table-wrap inventory-catalog-table-wrap">
        <table className="inventory-table inventory-catalog-table">
          <thead><tr><th>Name</th><th>Code</th>{tab==="service"&&<th>Group</th>}<th>Status</th><th>Usage</th><th>Updated</th><th>Actions</th></tr></thead>
          <tbody>{rows.map((row:any)=><tr key={row.id} className={!row.is_active?"inventory-row-archived":""}>
            <td><strong>{row.display_name}</strong></td>
            <td>{row.code}</td>
            {tab==="service"&&<td>{row.group_name}</td>}
            <td><span className={"inventory-master-status "+(row.is_active?"active":"archived")}>{row.is_active?"Active":"Archived"}</span></td>
            <td>{tab==="gtb_environment"||tab==="ms_environment"?"—":tab==="application"?row.record_count+" records":tab==="group"?row.service_count+" services":row.configuration_count+" configs"}</td>
            <td><small>{new Date(row.updated_at).toLocaleString()}</small></td>
            <td><div className="inventory-master-actions">
              <button type="button" onClick={()=>setHistory({type:historyType,id:row.id,name:row.display_name})}><History size={14}/>History</button>
              {row.is_active?<><button type="button" onClick={()=>startEdit(row)}><Pencil size={14}/>Edit</button><button type="button" className="danger" disabled={busy} onClick={()=>void archive(row)}><Archive size={14}/>Remove</button></>:<button type="button" disabled={busy} onClick={()=>void restore(row)}><RotateCcw size={14}/>Restore</button>}
            </div></td>
          </tr>)}</tbody>
        </table>
      </div>

      {editing&&<form className="inventory-catalog-editor" onSubmit={save}>
        <div className="inventory-catalog-editor-heading"><strong>{editing.id?"Edit":"Add"} {editing.kind==="gtb_environment"?"GTB environment":editing.kind==="ms_environment"?"Microservices environment":editing.kind}</strong><button type="button" onClick={()=>setEditing(null)}><X size={15}/></button></div>
        {editing.kind==="service"&&<label>Group<select required value={editing.group_id||0} onChange={e=>setEditing({...editing,group_id:Number(e.target.value)})}><option value={0}>Select group</option>{groups.filter(g=>g.is_active).map(g=><option key={g.id} value={g.id}>{g.display_name}</option>)}</select></label>}
        <label>Code / Name<input required value={editing.code} onChange={e=>setEditing({...editing,code:e.target.value})}/></label>
        <label>Display name<input value={editing.display_name} onChange={e=>setEditing({...editing,display_name:e.target.value})}/></label>
        <button className="primary-button" disabled={busy}>{busy?"Saving...":"Save"}</button>
      </form>}

      {history&&<InventoryHistoryModal token={token} entityType={history.type} entityId={history.id} entityName={history.name} onClose={()=>setHistory(null)}/>}
    </article>
  </div>;
}
