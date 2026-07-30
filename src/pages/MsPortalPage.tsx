import { FormEvent, useState } from "react";
import { createPipelineRequest } from "../services/api";
import type { ApplicationType, PipelineRequestInput } from "../types";

interface Props { token: string; onCreated: () => void; }

const APP_OWNERS: Record<ApplicationType, string> = {
  H2H: "Nagarajs@mashreq.com",
  "Native-Mobile": "mujahid@mashreq.com",
  Collections: "mohanreddy1@mashreq.com",
  Safenet: "krishnakants@mashreq.com",
};

const LANGUAGE_PORTS: Record<string, number> = {
  "java-maven": 8080,
  node: 3000,
  python: 8000,
  container: 8080,
};

const initial: PipelineRequestInput = {
  application_type: "H2H",
  app_owner: APP_OWNERS.H2H,
  repository_name: "",
  reference_repository_name: "",
  reference_branch: "",
  setup_pipeline: false,
  pipeline_type: "",
  ingress_path: "/api/",
  create_service: false,
  service_name: "",
  service_port: 8080,
  namespace: "",
  comments: "",
};

export default function MsPortalPage({ token, onCreated }: Props) {
  const [form, setForm] = useState(initial);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function setApplicationType(applicationType: ApplicationType) {
    setForm((current) => ({
      ...current,
      application_type: applicationType,
      app_owner: APP_OWNERS[applicationType],
    }));
  }

  function setRepositoryName(value: string) {
    const normalized = value
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^[-_]+|[-_]+$/g, "");
    const serviceName = normalized.replace(/_/g, "-");
    setForm((current) => ({
      ...current,
      repository_name: normalized,
      ingress_path: `/api/${normalized}`,
      service_name: serviceName,
    }));
  }

  function setLanguage(value: string) {
    setForm((current) => ({
      ...current,
      pipeline_type: value,
      service_port: LANGUAGE_PORTS[value] ?? current.service_port,
    }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true); setError(""); setMessage("");
    try {
      const created = await createPipelineRequest(form, token);
      setMessage(`${created.id} submitted to ${created.app_owner} for application-owner approval.`);
      setForm(initial);
      onCreated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Submission failed");
    } finally { setLoading(false); }
  }

  return <section>
    <div className="section-heading"><div><span className="eyebrow">SELF-SERVICE</span><h2>New Pipeline Request Wizard</h2><p>Submit the service details for application-owner approval. Namespace, pipeline setup and Kubernetes service decisions are completed by DevOps after approval.</p></div></div>
    <form className="form-card two-column" onSubmit={submit}>
      <label>Application<select value={form.application_type} onChange={(e) => setApplicationType(e.target.value as ApplicationType)}><option value="H2H">H2H</option><option value="Collections">Collections</option><option value="Native-Mobile">Native-Mobile</option><option value="Safenet">Safenet</option></select></label>
      <label>Application Owner<input disabled value={form.app_owner} /></label>
      <label>Repository Name<input required value={form.repository_name} onChange={(e) => setRepositoryName(e.target.value)} placeholder="payment_api-service" /><small>Lowercase letters, numbers, underscores and hyphens are supported.</small></label>
      <label>Reference Repository Name <small>(Optional)</small><input value={form.reference_repository_name} onChange={(e) => setForm({ ...form, reference_repository_name: e.target.value.trim() })} placeholder="h2h-reference-service" /></label>
      <label>Type of Language<select required value={form.pipeline_type} onChange={(e) => setLanguage(e.target.value)}><option value="">Select language</option><option value="java-maven">Java / Maven</option><option value="node">Node.js</option><option value="python">Python</option><option value="container">Container only</option></select></label>
      <label>Service Port<input type="number" min="1" max="65535" value={form.service_port} onChange={(e) => setForm({ ...form, service_port: Number(e.target.value) })} /><small>Automatically selected from the language and can be changed.</small></label>
      <label className="full-width">Ingress Path<input required value={form.ingress_path} onChange={(e) => setForm({ ...form, ingress_path: e.target.value })} /></label>
      <label className="full-width">Comments<textarea rows={4} value={form.comments} onChange={(e) => setForm({ ...form, comments: e.target.value })} /></label>
      {error && <div className="form-error full-width">{error}</div>}{message && <div className="form-success full-width">{message}</div>}
      <div className="form-actions full-width"><button className="primary-button" disabled={loading}>{loading ? "Submitting and emailing app owner..." : "Submit for App Owner Approval"}</button></div>
    </form>
  </section>;
}
