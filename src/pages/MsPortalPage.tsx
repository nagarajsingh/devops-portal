import { FormEvent, useEffect, useState } from "react";
import { createPipelineRequest, getNamespaces } from "../services/api";
import type { PipelineRequestInput } from "../types";

interface Props { token: string; onCreated: () => void; }

const initial: PipelineRequestInput = {
  application_type: "H2H",
  repository_name: "",
  reference_repository_name: "",
  reference_branch: "",
  setup_pipeline: false,
  pipeline_type: "",
  ingress_path: "/api/",
  create_service: true,
  service_name: "",
  service_port: 8080,
  namespace: "",
  comments: "",
};

export default function MsPortalPage({ token, onCreated }: Props) {
  const [form, setForm] = useState(initial);
  const [namespaces, setNamespaces] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getNamespaces(token).then((items) => {
      setNamespaces(items);
      setForm((current) => ({ ...current, namespace: current.namespace || items[0] || "" }));
    }).catch((reason) => setError(reason.message));
  }, [token]);

  function setRepositoryName(value: string) {
    const normalized = value.toLowerCase().trim().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "");
    setForm((current) => ({ ...current, repository_name: normalized, ingress_path: `/api/${normalized}`, service_name: normalized }));
  }

  function setReferenceRepository(value: string) {
    const reference = value.trim();
    setForm((current) => ({
      ...current,
      reference_repository_name: reference,
      setup_pipeline: reference ? true : false,
      reference_branch: reference ? current.reference_branch : "",
    }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true); setError(""); setMessage("");
    try {
      const created = await createPipelineRequest(form, token);
      setMessage(`${created.id} submitted successfully.`);
      setForm({ ...initial, namespace: namespaces[0] || "" });
      onCreated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Submission failed");
    } finally { setLoading(false); }
  }

  return <section>
    <div className="section-heading"><div><span className="eyebrow">SELF-SERVICE</span><h2>New Pipeline Request Wizard</h2><p>Create a repository request. A reference repository is optional for new or empty services.</p></div></div>
    <form className="form-card two-column" onSubmit={submit}>
      <label>Application<select value={form.application_type} onChange={(e) => setForm({ ...form, application_type: e.target.value as PipelineRequestInput["application_type"] })}><option value="H2H">H2H</option><option value="Collections">Collections</option><option value="Native-Mobile">Native-Mobile</option><option value="Safenet">Safenet</option></select></label>
      <label>Repository Name<input required value={form.repository_name} onChange={(e) => setRepositoryName(e.target.value)} placeholder="payment-api" /></label>
      <label>Reference Repository Name <small>(Optional)</small><input value={form.reference_repository_name} onChange={(e) => setReferenceRepository(e.target.value)} placeholder="h2h-reference-service" /></label>
      <label>Pipeline Setup<select value={String(form.setup_pipeline)} onChange={(e) => setForm({ ...form, setup_pipeline: e.target.value === "true" })}><option value="true">Yes</option><option value="false">No</option></select></label>
      <label>Pipeline Type<select value={form.pipeline_type} onChange={(e) => setForm({ ...form, pipeline_type: e.target.value })}><option value="">Optional</option><option value="java-maven">Java / Maven</option><option value="node">Node.js</option><option value="python">Python</option><option value="container">Container only</option></select></label>
      <label>Ingress Details<input required value={form.ingress_path} onChange={(e) => setForm({ ...form, ingress_path: e.target.value })} /></label>
      <label>Create Kubernetes Service<select value={String(form.create_service)} onChange={(e) => setForm({ ...form, create_service: e.target.value === "true" })}><option value="true">True</option><option value="false">False</option></select></label>
      <label>Service Name<input disabled={!form.create_service} required={form.create_service} value={form.service_name} onChange={(e) => setForm({ ...form, service_name: e.target.value })} /></label>
      <label>Service Port<input disabled={!form.create_service} type="number" min="1" max="65535" value={form.service_port} onChange={(e) => setForm({ ...form, service_port: Number(e.target.value) })} /></label>
      <label>Namespace<select required value={form.namespace} onChange={(e) => setForm({ ...form, namespace: e.target.value })}><option value="">Select namespace</option>{namespaces.map((item) => <option key={item}>{item}</option>)}</select></label>
      <label className="full-width">Comments<textarea rows={4} value={form.comments} onChange={(e) => setForm({ ...form, comments: e.target.value })} /></label>
      {error && <div className="form-error full-width">{error}</div>}{message && <div className="form-success full-width">{message}</div>}
      <div className="form-actions full-width"><button className="primary-button" disabled={loading}>{loading ? "Submitting..." : "Submit Pipeline Request"}</button></div>
    </form>
  </section>;
}
