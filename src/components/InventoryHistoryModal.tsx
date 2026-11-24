import { useEffect, useState } from "react";
import { History, Search, X } from "lucide-react";
import { getInventoryHistory } from "../services/api";
import type { InventoryHistoryEvent } from "../types";

type Props={
  token:string;
  entityType?:string;
  entityId?:number|null;
  entityName?:string;
  onClose:()=>void;
};

function displayValue(value:string|null){
  if(value===null||value==="")return "—";
  try{
    const parsed=JSON.parse(value);
    return typeof parsed==="string"?parsed:JSON.stringify(parsed);
  }catch{return value;}
}

export default function InventoryHistoryModal({token,entityType="",entityId=null,entityName="",onClose}:Props){
  const [rows,setRows]=useState<InventoryHistoryEvent[]>([]);
  const [query,setQuery]=useState("");
  const [actor,setActor]=useState("");
  const [action,setAction]=useState("");
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");

  useEffect(()=>{
    const timer=window.setTimeout(()=>{
      setLoading(true);setError("");
      getInventoryHistory(token,{entity_type:entityType||undefined,entity_id:entityId||undefined,q:query||undefined,actor:actor||undefined,action:action||undefined,limit:500})
        .then(setRows)
        .catch(e=>setError(e instanceof Error?e.message:"Unable to load inventory history"))
        .finally(()=>setLoading(false));
    },150);
    return()=>window.clearTimeout(timer);
  },[token,entityType,entityId,query,actor,action]);

  return <div className="inventory-modal-backdrop" onMouseDown={onClose}>
    <article className="inventory-modal inventory-history-modal" onMouseDown={e=>e.stopPropagation()}>
      <button type="button" className="inventory-modal-close" onClick={onClose}><X size={19}/></button>
      <div className="inventory-modal-heading">
        <div className="inventory-card-icon"><History size={22}/></div>
        <div>
          <span className="eyebrow">{entityId?"ITEM HISTORY":"INVENTORY AUDIT HISTORY"}</span>
          <h2>{entityName||"All inventory changes"}</h2>
          <p>Shows who changed what, the previous value, the new value, source and exact time.</p>
        </div>
      </div>
      {!entityId&&<div className="inventory-history-filters">
        <label><Search size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search item, field or value..."/></label>
        <input value={actor} onChange={e=>setActor(e.target.value)} placeholder="Changed by"/>
        <select value={action} onChange={e=>setAction(e.target.value)}>
          <option value="">All actions</option>
          <option value="CREATE">Created</option>
          <option value="UPDATE">Updated</option>
          <option value="ARCHIVE">Archived / removed</option>
          <option value="RESTORE">Restored</option>
          <option value="ACCESS">Credential access</option>
        </select>
      </div>}
      {error&&<div className="inventory-notice error">{error}</div>}
      <div className="inventory-history-table-wrap">
        <table className="inventory-table inventory-history-table">
          <thead><tr><th>Date / Time</th><th>Item</th><th>Action</th><th>Field</th><th>Old value</th><th>New value</th><th>Changed by</th><th>Source</th></tr></thead>
          <tbody>
            {rows.map(row=><tr key={row.id}>
              <td><small>{new Date(row.created_at).toLocaleString()}</small></td>
              <td><strong>{row.entity_name}</strong><small className="inventory-history-type">{row.entity_type}{row.entity_id?" #"+row.entity_id:""}</small></td>
              <td><span className={"inventory-history-action "+row.action.toLowerCase()}>{row.action}</span></td>
              <td>{row.field_name||"—"}</td>
              <td className="inventory-history-value">{displayValue(row.old_value)}</td>
              <td className="inventory-history-value">{displayValue(row.new_value)}</td>
              <td>{row.actor}</td>
              <td>{row.source}</td>
            </tr>)}
            {!loading&&rows.length===0&&<tr><td colSpan={8}><div className="inventory-empty">No history found.</div></td></tr>}
          </tbody>
        </table>
        {loading&&<div className="inventory-loading-inline">Loading history...</div>}
      </div>
    </article>
  </div>;
}
