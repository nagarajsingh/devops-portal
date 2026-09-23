import { ArrowRight, ClipboardList, GitCompareArrows, Rocket } from "lucide-react";
import type { PageKey, Role } from "../types";

interface HomePageProps { onNavigate: (page: PageKey) => void; role: Role; }

export default function HomePage({ onNavigate, role }: HomePageProps) {
  return <section className="page-grid">
    <article className="welcome-panel">
      <span className="eyebrow">NeoCorp Devops</span>
      <h1>Welcome to the DevOps Portal</h1>
      <p>Submit pipeline onboarding requests and track platform activities from one place.</p>
      <div className="welcome-actions">
        <button className="primary-button" onClick={() => onNavigate("ms-portal")}><Rocket size={18} />Create MS Request<ArrowRight size={17} /></button>
        <button className="secondary-button" onClick={() => onNavigate("requests")}><ClipboardList size={18} />View My Requests</button>
      </div>
    </article>
    <article className="info-card"><h3>Quick start</h3><p>Application name automatically populates repository, ingress and Kubernetes service names. You can edit them before submission.</p></article>
    {role === "devops" && <article className="info-card devops-home-tool-card">
      <div className="devops-home-tool-icon"><GitCompareArrows size={24}/></div>
      <div>
        <span className="eyebrow">DEVOPS ONLY</span>
        <h3>SIT → UAT Repo Sync</h3>
        <p>Create or update <strong>release/uat</strong> from develop and generate UAT Helm files from existing SIT configuration across one or more Azure DevOps repositories.</p>
        <button className="secondary-button" onClick={() => onNavigate("repo-sync")}>Open Repo Sync<ArrowRight size={16}/></button>
      </div>
    </article>}
  </section>;
}
