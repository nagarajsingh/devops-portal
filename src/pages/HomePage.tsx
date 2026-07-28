export default function HomePage() {
  return (
    <section className="page-grid">
      <article className="welcome-panel">
        <span className="eyebrow">MASHREQ NEO CORP</span>
        <h1>Welcome to the DevOps Portal</h1>
        <p>Access engineering services, submit microservice requests and track platform activities from one place.</p>
        <div className="welcome-actions">
          <button className="primary-button">Create MS request</button>
          <button className="secondary-button">View my requests</button>
        </div>
      </article>
      <article className="info-card"><h3>Quick start</h3><p>Use the search bar to locate a portal feature or open a service from the navigation.</p></article>
    </section>
  );
}
