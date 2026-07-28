const services = [
  ["Kubernetes clusters", "Healthy", "12/12 clusters available"],
  ["Build pipelines", "Healthy", "28 successful today"],
  ["Application services", "Warning", "2 services need attention"],
];
export default function MonitoringPage() {
  return <section><div className="section-heading"><div><span className="eyebrow">ADMIN SERVICE</span><h2>Monitoring</h2></div></div><div className="service-grid">{services.map(([name,status,detail]) => <article className="service-card" key={name}><div><h3>{name}</h3><p>{detail}</p></div><span className={`health ${status.toLowerCase()}`}>{status}</span></article>)}</div></section>;
}
