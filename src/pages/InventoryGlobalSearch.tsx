import { FormEvent, useState } from "react";
import { Database, Search, Server, Wrench, X } from "lucide-react";
import { searchInventory } from "../services/api";
import type { InventorySearchResult } from "../types";

export default function InventoryGlobalSearch({token}:{token:string}){
  const [query,setQuery]=useState("");
  const [result,setResult]=useState<InventorySearchResult|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");

  async function run(event?:FormEvent){
    event?.preventDefault();
    const value=query.trim();
    if(value.length<2){setResult(null);setError("Enter at least 2 characters.");return;}
    setLoading(true);setError("");
    try{setResult(await searchInventory(value,token));}
    catch(reason){setError(reason instanceof Error?reason.message:"Unable to search Inventory");setResult(null);}
    finally{setLoading(false);}
  }

  function clear(){setQuery("");setResult(null);setError("");}

  return <section className="inventory-global-search">
    <div className="inventory-global-search-heading">
      <div><span className="eyebrow">UNIFIED INVENTORY SEARCH</span><h2>Find anything across Inventory</h2><p>Search server IP, hostname, application, service, database, owner, CR number, status or comments.</p></div>
    </div>
    <form onSubmit={run} className="inventory-global-search-form">
      <Search size={20}/>
      <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Example: 10.210.36.26, H2H, native-mobile-auth-management, CRQ000000167008..."/>
      {query&&<button type="button" className="inventory-search-clear" onClick={clear}><X size={16}/></button>}
      <button className="primary-button" disabled={loading||query.trim().length<2}>{loading?"Searching...":"Search"}</button>
    </form>
    {error&&<div className="inventory-notice error">{error}</div>}
    {result&&<div className="inventory-global-results">
      <div className="inventory-search-result-summary"><strong>{result.total}</strong><span>matches for “{result.query}”</span></div>

      <div className="inventory-search-groups">
        <article className="inventory-search-group">
          <header><Database size={18}/><div><strong>GTB</strong><span>{result.gtb.length} matches</span></div></header>
          <div className="inventory-search-result-list">
            {result.gtb.map(item=><div className="inventory-search-result-card" key={`gtb-${item.id}`}>
              <div><span className="inventory-result-kicker">{item.application} · {item.environment}</span><strong>{item.hostname||item.ip_address||item.app_name}</strong></div>
              <dl><div><dt>IP</dt><dd>{item.ip_address||"—"}</dd></div><div><dt>Hostname</dt><dd>{item.hostname||"—"}</dd></div><div><dt>Type</dt><dd>{item.asset_type||"—"}</dd></div><div><dt>App Name</dt><dd>{item.app_name||"—"}</dd></div></dl>
              {item.console_details&&<p>{item.console_details}</p>}
            </div>)}
            {!result.gtb.length&&<div className="inventory-search-empty">No GTB matches.</div>}
          </div>
        </article>

        <article className="inventory-search-group">
          <header><Server size={18}/><div><strong>Microservices</strong><span>{result.microservices.length} matches</span></div></header>
          <div className="inventory-search-result-list">
            {result.microservices.map(item=><div className="inventory-search-result-card" key={`ms-${item.id}`}>
              <div><span className="inventory-result-kicker">{item.group} · {item.environment}</span><strong>{item.service}</strong></div>
              <dl><div><dt>Connection</dt><dd>{item.connection_name}</dd></div><div><dt>DB URL</dt><dd>{item.db_url||"—"}</dd></div><div><dt>DB Name</dt><dd>{item.db_name||"—"}</dd></div><div><dt>DB User</dt><dd>{item.db_username||"—"}</dd></div></dl>
            </div>)}
            {!result.microservices.length&&<div className="inventory-search-empty">No Microservices matches.</div>}
          </div>
        </article>

        <article className="inventory-search-group">
          <header><Wrench size={18}/><div><strong>Patching</strong><span>{result.patching.length} matches</span></div></header>
          <div className="inventory-search-result-list">
            {result.patching.map(item=><div className="inventory-search-result-card" key={`patch-${item.id}`}>
              <div><span className="inventory-result-kicker">{item.environment_class.replace("_","-")} · {item.source_type}</span><strong>{item.hostname||item.asset_identifier}</strong></div>
              <dl><div><dt>IP / Cluster</dt><dd>{item.asset_identifier}</dd></div><div><dt>Application</dt><dd>{item.application||"—"}</dd></div><div><dt>Status</dt><dd>{item.status.replaceAll("_"," ")}</dd></div><div><dt>CR</dt><dd>{item.cr_number||"—"}</dd></div></dl>
              {item.comments&&<p>{item.comments}</p>}
            </div>)}
            {!result.patching.length&&<div className="inventory-search-empty">No Patching matches.</div>}
          </div>
        </article>
      </div>
    </div>}
  </section>;
}
