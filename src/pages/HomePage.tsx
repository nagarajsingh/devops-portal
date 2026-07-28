import { ArrowRight, ClipboardList, Rocket } from "lucide-react";
import type { PageKey } from "../types";

interface HomePageProps {
  onNavigate: (page: PageKey) => void;
  onOpenMsSetup: () => void;
}

export default function HomePage({ onNavigate, onOpenMsSetup }: HomePageProps) {
  return (
    <section className="page-grid">
      <article className="welcome-panel">
        <span className="eyebrow">MASHREQ NEO CORP</span>
        <h1>Welcome to the DevOps Portal</h1>
        <p>
          Access engineering services, submit microservice requests and track
          platform activities from one place.
        </p>

        <div className="welcome-actions">
          <button className="primary-button" onClick={onOpenMsSetup}>
            <Rocket size={18} />
            Create MS Request
            <ArrowRight size={17} />
          </button>

          <button
            className="secondary-button"
            onClick={() => onNavigate("requests")}
          >
            <ClipboardList size={18} />
            View My Requests
          </button>
        </div>
      </article>

      <article className="info-card">
        <h3>Quick start</h3>
        <p>
          Create a new microservice onboarding request or review the requests
          you have already submitted.
        </p>
      </article>
    </section>
  );
}
