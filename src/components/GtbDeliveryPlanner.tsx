import { FormEvent, useEffect, useState } from "react";
import { getDeliveryCatalog, planDelivery, type DeliveryCatalog, type DeliveryPlan } from "../services/api";

export default function GtbDeliveryPlanner({ token }: { token:string }) {
  const [catalog, setCatalog] = useState<DeliveryCatalog | null>(null);
  const [application, setApplication] = useState("GTB-Applications");
  const [component, setComponent] = useState("");
  const [country, setCountry] = useState("Egypt");
  const [environment, setEnvironment] = useState("R2UAT");
  const [vendorBranch, setVendorBranch] = useState("");
  const [buildBranch, setBuildBranch] = useState("release/uat");
  const [war, setWar] = useState("None");
  const [jar, setJar] = useState("None");
  const [deployType, setDeployType] = useState("Regular");
  const [image, setImage] = useState("");
  const [useImage, setUseImage] = useState(true);
  const [listOnly, setListOnly] = useState(false);
  const [plan, setPlan] = useState<DeliveryPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { let cancelled=false; getDeliveryCatalog(token).then(data => { if(!cancelled) setCatalog(data); }).catch(e => { if(!cancelled) setError(e.message); }); return () => {cancelled=true;}; }, [token]);
  const components = application === "Collections" ? catalog?.collections_components[country] ?? [] : catalog?.gtb_components ?? [];
  const selected = components.includes(component) ? component : components[0] ?? "";
  async function submit(event:FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setPlan(null);
    try { setPlan(await planDelivery({application,component:selected,country,environment,vendor_branch:vendorBranch,build_branch:buildBranch,war_files:war,jar_files:jar,deploy_type:deployType,vendor_image:image,use_vendor_image:useImage,list_only:listOnly},token)); }
    catch(e) {setError(e instanceof Error?e.message:"Unable to prepare the plan");} finally {setBusy(false);}
  }
  return <article className="gtb-panel">
    <h2>GTB & Collections delivery planner</h2><p>Resolve the working pipeline contracts from Collections-Dashboard and review each dependency before execution.</p>
    {error && <p className="gtb-error" role="alert">{error}</p>}
    <form onSubmit={submit} onChange={()=>setPlan(null)}><fieldset disabled={busy} className="gtb-delivery-form">
      <label>Application<select value={application} onChange={e=>setApplication(e.target.value)}><option>GTB-Applications</option><option>Collections</option></select></label>
      {application==="Collections" && <label>Country<select value={country} onChange={e=>setCountry(e.target.value)}><option>Egypt</option><option>UAE</option></select></label>}
      <label>Component<select value={selected} onChange={e=>setComponent(e.target.value)} required>{!components.length && <option value="">Loading components…</option>}{components.map(value=><option key={value}>{value}</option>)}</select></label>
      {application==="GTB-Applications" ? <>
        <label>Build environment<select value={environment} onChange={e=>setEnvironment(e.target.value)}>{(catalog?.environments ?? ["R2UAT"]).map(value=><option key={value}>{value}</option>)}</select></label>
        <label>Vendor branch<input value={vendorBranch} onChange={e=>setVendorBranch(e.target.value)} maxLength={200} placeholder="Branch from the vendor release document"/></label>
        <label>Build source branch<input value={buildBranch} onChange={e=>setBuildBranch(e.target.value)} required maxLength={200}/></label>
        <label>WAR files<input value={war} onChange={e=>setWar(e.target.value)} maxLength={2000}/></label>
        <label>JAR files<input value={jar} onChange={e=>setJar(e.target.value)} maxLength={2000}/></label>
        <label>Deployment type<input value={deployType} onChange={e=>setDeployType(e.target.value)} required maxLength={80}/></label>
        <label className="gtb-check"><input type="checkbox" checked={listOnly} onChange={e=>setListOnly(e.target.checked)}/>List-only code pull</label>
      </> : <>
        <label>Vendor image<input value={image} onChange={e=>setImage(e.target.value)} maxLength={500} placeholder="registry/service:tag"/></label>
        <label className="gtb-check"><input type="checkbox" checked={useImage} onChange={e=>setUseImage(e.target.checked)}/>Use vendor image</label>
      </>}
      <button className="primary-button" disabled={busy||!selected}>{busy?"Preparing…":"Prepare delivery plan"}</button>
    </fieldset></form>
    {plan && <div className="gtb-delivery-result" aria-live="polite"><h3>Plan for {plan.application} / {plan.component}</h3>
      {plan.blockers.length>0 && <div className="gtb-error"><strong>Resolve before execution</strong><ul>{plan.blockers.map((text,i)=><li key={i}>{text}</li>)}</ul></div>}
      <ol>{plan.steps.map(step=><li key={step.id}><strong>{step.title}</strong><p>{step.gate}</p><details><summary>Resolved contract · {step.id}</summary><pre>{JSON.stringify(step,null,2)}</pre></details></li>)}</ol>
      {plan.notes.map((text,i)=><p key={i}>{text}</p>)}<p><a href="/devops-portal/deployment-management">Open Deployment Management</a></p>
    </div>}
  </article>;
}
