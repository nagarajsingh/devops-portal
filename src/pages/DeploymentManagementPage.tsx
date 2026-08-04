import { useEffect, useRef, useState } from "react";
import { CheckCircle2, FileText, GitPullRequest, Play, Rocket, UploadCloud } from "lucide-react";

const API_BASE = "/devops-portal/api";

type Extracted = {
  filename?: string;
  application: string;
  branch_name: string;
  environment: string;
  war_files: string[];
  jar_files: string[];
  text_preview?: string;
  confidence?: Record<string, string>;
};

type DeploymentRequest = Extracted & {
  id: string;
  app_owner: string;
  repository: string;
  target_branch: string;
  status: string;
  requested_by: string;
  created_at: string;
  steps: Record<string, { status: string }>;
};

const emptyExtracted: Extracted = {
  application: "",
  branch_name: "",
  environment: "",
  war_files: [],
  jar_files: [],
};

export default function DeploymentManagementPage({ token, role }: { token: string; role: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [data, setData] = useState<Extracted>(emptyExtracted);
  const [appOwner, setAppOwner] = useState("");
  const [repository, setRepository] = useState("");
  const [targetBranch, setTargetBranch] = useState("release/uat");
  const [requests, setRequests] = useState<DeploymentRequest[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "error" | "info">("info");
  const [extracted, setExtracted] = useState(false);
  const resultRef = useRef<HTMLDivElement | null>(null);

  async function loadRequests() {
    try {
      const response = await fetch(`${API_BASE}/deployment-management/requests`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) setRequests(await response.json());
    } catch {
      // Keep the page usable even when queue refresh temporarily fails.
    }
  }

  useEffect(() => { void loadRequests(); }, [token]);

  async function extract() {
    if (!file || busy) return;

    setBusy(true);
    setExtracted(false);
    setMessage("Extracting release details from the uploaded document...");
    setMessageType("info");

    try {
      const form = new FormData();
      form.append("document", file);

      const response = await fetch(`${API_BASE}/deployment-management/extract`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });

      const body = await response.json().catch(() => ({ detail: "Invalid response from backend" }));
      if (!response.ok) {
        setMessage(body.detail || "Unable to extract document");
        setMessageType("error");
        return;
      }

      const extractedData: Extracted = {
        filename: body.filename || file.name,
        application: body.application || "",
        branch_name: body.branch_name || "",
        environment: body.environment || "",
        war_files: Array.isArray(body.war_files) ? body.war_files : [],
        jar_files: Array.isArray(body.jar_files) ? body.jar_files : [],
        text_preview: body.text_preview || "",
        confidence: body.confidence || {},
      };

      setData(extractedData);
      setRepository(extractedData.application || "");
      setExtracted(true);

      const foundCount = [
        extractedData.application,
        extractedData.branch_name,
        extractedData.environment,
      ].filter(Boolean).length;

      setMessage(
        foundCount > 0
          ? `Document processed successfully. ${foundCount} of 3 primary fields were detected. Review and complete the form before submitting.`
          : "Document processed, but application, branch and environment were not detected. Review the extracted text preview and enter the values manually.",
      );
      setMessageType(foundCount > 0 ? "success" : "info");

      window.setTimeout(() => {
        resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 100);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to connect to the extraction service");
      setMessageType("error");
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (busy) return;
    setBusy(true);
    setMessage("Submitting deployment request...");
    setMessageType("info");

    try {
      const response = await fetch(`${API_BASE}/deployment-management/requests`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          ...data,
          app_owner: appOwner,
          repository,
          target_branch: targetBranch,
          document_name: file?.name || data.filename || "",
        }),
      });
      const body = await response.json().catch(() => ({ detail: "Invalid response from backend" }));
      if (!response.ok) {
        setMessage(body.detail || "Unable to submit deployment request");
        setMessageType("error");
        return;
      }

      setMessage(`Deployment request ${body.id} submitted for application-owner approval.`);
      setMessageType("success");
      await loadRequests();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to submit deployment request");
      setMessageType("error");
    } finally {
      setBusy(false);
    }
  }

  async function action(id: string, name: string) {
    const pat = name === "trigger-code-pull" ? window.prompt("Azure DevOps PAT") || "" : "";
    try {
      const response = await fetch(`${API_BASE}/deployment-management/requests/${id}/${name}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ azure_devops_pat: pat || null }),
      });
      const body = await response.json().catch(() => ({ detail: "Invalid response from backend" }));
      setMessage(response.ok ? `${id} updated successfully.` : body.detail || "Action failed");
      setMessageType(response.ok ? "success" : "error");
      if (response.ok) await loadRequests();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Action failed");
      setMessageType("error");
    }
  }

  return <div className="deployment-management-page">
    <section className="deployment-hero">
      <div><span className="eyebrow">RELEASE ORCHESTRATION</span><h1>Deployment Management Dashboard</h1><p>Upload release documents, capture approval, orchestrate code pull, review pull requests, and trigger parameterized builds from one controlled workflow.</p></div>
      <Rocket size={44}/>
    </section>

    <div className="deployment-workflow">
      {["Release document", "App-owner approval", "DevOps review", "Code pull", "Pull request", "Build & deploy"].map((label, index) => <div key={label}><span>{index + 1}</span><strong>{label}</strong></div>)}
    </div>

    <section className="deployment-grid">
      <article className="deployment-card">
        <div className="deployment-card-title"><UploadCloud/><div><h2>New deployment request</h2><p>PDF and DOCX fields remain editable before submission.</p></div></div>
        <label className="deployment-upload"><FileText/><input type="file" accept=".pdf,.docx,.txt,.md" onChange={(event) => {
          const selected = event.target.files?.[0] || null;
          setFile(selected);
          setData(emptyExtracted);
          setRepository("");
          setExtracted(false);
          setMessage(selected ? `${selected.name} selected. Click Extract release details.` : "");
          setMessageType("info");
        }}/><span>{file?.name || "Choose release document"}</span></label>
        <button className="primary-button" disabled={!file || busy} onClick={extract}>{busy ? "Processing..." : "Extract release details"}</button>

        {message && <div className={`deployment-message ${messageType}`}>{message}</div>}

        <div className={`deployment-extraction-result ${extracted ? "visible" : ""}`} ref={resultRef}>
          {extracted && <>
            <div className="deployment-result-header">
              <div><span className="eyebrow">EXTRACTION RESULT</span><h3>Review detected release details</h3></div>
              <span className="status healthy">Document processed</span>
            </div>
            <div className="deployment-result-summary">
              <div><span>Application</span><strong>{data.application || "Not detected"}</strong></div>
              <div><span>Branch</span><strong>{data.branch_name || "Not detected"}</strong></div>
              <div><span>Environment</span><strong>{data.environment || "Not detected"}</strong></div>
              <div><span>Artifacts</span><strong>{data.war_files.length + data.jar_files.length}</strong></div>
            </div>
            {data.text_preview && <details className="deployment-text-preview"><summary>View extracted document text</summary><pre>{data.text_preview}</pre></details>}
          </>}
        </div>

        <div className="deployment-form">
          <label>Application<input value={data.application} onChange={(e) => setData({...data, application:e.target.value})}/></label>
          <label>Source branch<input value={data.branch_name} onChange={(e) => setData({...data, branch_name:e.target.value})}/></label>
          <label>Environment<input value={data.environment} onChange={(e) => setData({...data, environment:e.target.value})}/></label>
          <label>Application owner<input value={appOwner} onChange={(e) => setAppOwner(e.target.value)} placeholder="owner@mashreq.com"/></label>
          <label>Repository<input value={repository} onChange={(e) => setRepository(e.target.value)}/></label>
          <label>PR target branch<input value={targetBranch} onChange={(e) => setTargetBranch(e.target.value)}/></label>
          <label>WAR files<input value={data.war_files.join(", ")} onChange={(e) => setData({...data, war_files:e.target.value.split(",").map(v=>v.trim()).filter(Boolean)})}/></label>
          <label>JAR files<input value={data.jar_files.join(", ")} onChange={(e) => setData({...data, jar_files:e.target.value.split(",").map(v=>v.trim()).filter(Boolean)})}/></label>
        </div>
        <button className="primary-button" disabled={busy || !data.application || !data.branch_name || !data.environment || !appOwner} onClick={submit}>Submit for application-owner approval</button>
      </article>

      <article className="deployment-card deployment-queue">
        <div className="deployment-card-title"><GitPullRequest/><div><h2>Deployment queue</h2><p>Live workflow status for release requests.</p></div></div>
        {requests.length === 0 ? <div className="monitoring-empty">No deployment requests yet.</div> : requests.slice(0,10).map((request) => <div className="deployment-request" key={request.id}>
          <div><span>{request.id}</span><h3>{request.application}</h3><p>{request.branch_name} → {request.environment}</p></div>
          <span className="status warning">{request.status}</span>
          <div className="deployment-step-row">{Object.entries(request.steps || {}).map(([key,value]) => <small key={key} title={key}><CheckCircle2 size={13}/>{value.status}</small>)}</div>
          {role === "devops" && <div className="deployment-actions">
            {request.status === "Pending App Owner Approval" && <button className="secondary-button" onClick={() => action(request.id,"owner-approve")}>Record owner approval</button>}
            {request.status === "Awaiting DevOps" && <button className="primary-button" onClick={() => action(request.id,"trigger-code-pull")}><Play size={15}/>Trigger code pull</button>}
          </div>}
        </div>)}
      </article>
    </section>
  </div>;
}
