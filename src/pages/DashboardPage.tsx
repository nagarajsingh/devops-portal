const stats = [
  ["My Requests", "12"],
  ["Pending Approval", "4"],
  ["In Progress", "3"],
  ["Completed", "5"],
];

export default function DashboardPage() {
  return <section><div className="section-heading"><div><span className="eyebrow">OVERVIEW</span><h2>Dashboard</h2></div></div><div className="stats-grid">{stats.map(([label,value]) => <article className="stat-card" key={label}><strong>{value}</strong><span>{label}</span></article>)}</div><article className="table-card"><h3>Recent activity</h3><table><thead><tr><th>Request</th><th>Service</th><th>Status</th></tr></thead><tbody><tr><td>MS-1042</td><td>Payment Notification</td><td><span className="status pending">Pending Approval</span></td></tr><tr><td>MS-1038</td><td>Trade Alerts</td><td><span className="status progress">In Progress</span></td></tr></tbody></table></article></section>;
}
