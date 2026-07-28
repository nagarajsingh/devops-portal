const requests = [
  {
    id: "MS-1023",
    service: "payment-api",
    namespace: "mobile-domain-dev",
    status: "Pending Approval",
    requestedOn: "Today",
  },
  {
    id: "MS-1022",
    service: "auth-service",
    namespace: "mobile-orchestration-dev",
    status: "Approved",
    requestedOn: "Yesterday",
  },
  {
    id: "MS-1019",
    service: "customer-profile",
    namespace: "h2h-dev",
    status: "Completed",
    requestedOn: "25 Jul 2026",
  },
];

export default function RequestsPage() {
  return (
    <section>
      <div className="section-heading">
        <div>
          <span className="eyebrow">SELF-SERVICE</span>
          <h2>My Requests</h2>
          <p>Track the status of your submitted microservice requests.</p>
        </div>
      </div>

      <div className="table-card">
        <table>
          <thead>
            <tr>
              <th>Request ID</th>
              <th>Service</th>
              <th>Namespace</th>
              <th>Status</th>
              <th>Requested On</th>
            </tr>
          </thead>
          <tbody>
            {requests.map((request) => (
              <tr key={request.id}>
                <td><strong>{request.id}</strong></td>
                <td>{request.service}</td>
                <td>{request.namespace}</td>
                <td>
                  <span className={`status ${request.status === "Pending Approval" ? "pending" : request.status === "Approved" ? "progress" : "healthy"}`}>
                    {request.status}
                  </span>
                </td>
                <td>{request.requestedOn}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
