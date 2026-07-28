import { ArrowRight, ClipboardList, Rocket } from "lucide-react";
import type { PageKey } from "../types";

interface HomePageProps { onNavigate: (page: PageKey) => void; }

export default function HomePage({ onNavigate }: HomePageProps) {
  return <section className="page-grid"><article className="welcome-panel"><span className="eyebrow">MASHREQ NEO CORP</span><h1>Welcome to the DevOps Portal</h1><p>Submit pipeline onboarding requests and track platform activities from one place.</p><div className="welcome-actions"><button className="primary-button" onClick={() => onNavigate("ms-portal")}><Rocket size={18} />Create MS Request<ArrowRight size={17} /></button><button className="secondary-button" onClick={() => onNavigate("requests")}><ClipboardList size={18} />View My Requests</button></div></article><article className="info-card"><h3>Quick start</h3><p>Application name automatically populates repository, ingress and Kubernetes service names. You can edit them before submission.</p></article></section>;
}
