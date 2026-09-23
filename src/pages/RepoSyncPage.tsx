import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, FileCode2, GitBranch, GitCompareArrows, RefreshCw, ShieldCheck } from "lucide-react";
import PremiumDeploymentModal from "../components/PremiumDeploymentModal";

const API_BASE = "/devops-portal/api";
const PAT_SESSION_KEY = "devops-portal-azure-pat";

type SyncFile = {
  source_path: string;
  target_path: string;
  action: "add" | "edit" | "unchanged";
};

type SyncResult = {
  repository: string;
  reference_repository: string;
  source_branch: string;
  target_branch: string;
  branch_action?: string;
  status?: string;
  message?: string;
  error?: string;
  url?: string;
  changed_files?: number;
  warnings: string[];
  files: SyncFile[];
};

type SyncResponse = {
  mode: "preview" | "execute";
  results: SyncResult[];
};

function readSessionPat() {
  try { return sessionStorage.getItem(PAT_SESSION_KEY) || ""; }
  catch { return ""; }
}

function parseTargets(value: string) {
  const seen = new Set<string>();
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item) return false;
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

async function readResponse(response: Response) {
  const text = await response.text();
  if (!text) return {};
  try { return JSON.parse(text); }
  catch { return { detail: text }; }
}

export default function RepoSyncPage({ token }: { token: string }) {
  const [referenceRepository, setReferenceRepository] = useState("");
  const [targetsText, setTargetsText] = useState("");
  const [pat, setPat] = useState(readSessionPat);
  const [patEditable, setPatEditable] = useState(false);
  const [preview, setPreview] = useState<SyncResponse | null>(null);
  const [result, setResult] = useState<SyncResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const targets = useMemo(() => parseTargets(targetsText), [targetsText]);
  const previewReady = !!preview?.results.length && preview.results.every((item) => !item.error);

  function persistPat(value: string) {
    setPat(value);
    try {
      if (value) sessionStorage.setItem(PAT_SESSION_KEY, value);
      else sessionStorage.removeItem(PAT_SESSION_KEY);
    } catch { /* browser session storage unavailable */ }
  }

  function invalidatePreview() {
    setPreview(null);
    setResult(null);
    setError("");
  }

  async function call(mode: "preview" | "execute") {
    if (!targets.length) {
      setError("Provide at least one Azure DevOps repository to update.");
      return;
    }
    if (!pat.trim()) {
      setError("Enter your Azure DevOps PAT for this browser session.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      const response = await fetch(${API_BASE}/repo-sync/${mode}, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          target_repositories: targets,
          reference_repository: referenceRepository.trim(),
          azure_devops_pat: pat,
        }),
      });
      const body = await readResponse(response);
      if (!response.ok) throw new Error(body.detail || `Repository ${mode} failed`);
      if (mode === "preview") {
        setPreview(body as SyncResponse);
        setResult(null);
      } else {
        setResult(body as SyncResponse);
        setPreview(body as SyncResponse);
      }
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Repository sync failed");
    } finally {
      setBusy(false);
    }
  }

  async function executeSync() {
    setConfirmOpen(false);
    await call("execute");
  }

  return <div className="repo-sync-page">
    <section className="repo-sync-hero">
      <div>
        <span className="eyebrow">DEVOPS · REPOSITORY PROMOTION</span>
        <h1>SIT → UAT Repository Sync</h1>
        <p>Create or refresh <strong>release/uat</strong> from <strong>develop</strong>, then generate UAT Helm configuration from the existing SIT configuration without modifying develop.</p>
      </div>
      <div className="repo-sync-hero-icon"><GitCompareArrows size={38}/></div>
    </section>

    <section className="repo-sync-flow">
      <div><span>BASE BRANCH</span><strong><GitBranch size={17}/>develop</strong><small>Application code + existing DEV/SIT files</small></div>
      <div className="repo-sync-flow-arrow">→</div>
      <div><span>SYNC LOGIC</span><strong><RefreshCw size={17}/>SIT configuration</strong><small>Repository name + SIT environment values adapted</small></div>
      <div className="repo-sync-flow-arrow">→</div>
      <div><span>TARGET BRANCH</span><strong><GitBranch size={17}/>release/uat</strong><small>Develop contents + generated UAT files</small></div>
    </section>

    <section className="repo-sync-card">
      <div className="repo-sync-section-title">
        <div><ShieldCheck/><div><h2>Configure repository sync</h2><p>Available only to DevOps users. Preview is required before the branch update is enabled.</p></div></div>
      </div>

      <div className="repo-sync-form-grid">
        <label className="full-width">
          Repositories to update
          <textarea
            rows={5}
            value={targetsText}
            onChange={(event) => { setTargetsText(event.target.value); invalidatePreview(); }}
            placeholder={"native-mobile-approval-bff\nnative-mobile-payment-bff\nnative-mobile-customer-service"}
          />
          <small>Enter one existing Azure DevOps repository per line or separate names with commas.</small>
        </label>

        <label>
          SIT reference repository <span className="optional-label">Optional</span>
          <input
            value={referenceRepository}
            onChange={(event) => { setReferenceRepository(event.target.value); invalidatePreview(); }}
            placeholder="Leave blank to use each target repo"
          />
          <small>If blank, each repository uses its own SIT files from develop. Set this only when you want all target repos to use a known-good SIT template repository.</small>
        </label>

        <label>
          Azure DevOps PAT
          <input
            type="password"
            name="uat-repo-sync-session-pat"
            value={pat}
            onChange={(event) => persistPat(event.target.value)}
            onFocus={() => setPatEditable(true)}
            readOnly={!patEditable}
            autoComplete="new-password"
            data-lpignore="true"
            data-1p-ignore="true"
            placeholder="Stored only for this browser session"
          />
          <small>{pat ? "PAT available for this session." : "Code read/write permission is required."}</small>
        </label>
      </div>

      <div className="repo-sync-scope">
        <div><FileCode2/><span>Generated automatically</span></div>
        <code>configmap-sit.yaml → configmap-uat.yaml</code>
        <code>secret-sit.yaml → secret-uat.yaml</code>
        <code>values-sit.yaml → values-uat.yaml</code>
        <p>Any additional <strong>*-sit.yaml/yml</strong> file under <strong>BuildAndPublish</strong> is also promoted. Existing Chart.yaml, deployment.yaml, service.yaml, DEV and SIT files remain inherited from develop.</p>
      </div>

      {error && <div className="repo-sync-inline error"><AlertTriangle size={17}/><span>{error}</span></div>}

      <div className="repo-sync-actions">
        <button className="secondary-button" disabled={busy || !targets.length} onClick={() => void call("preview")}>
          <GitCompareArrows size={16}/>{busy ? "Checking repositories..." : "Preview UAT sync"}
        </button>
        <button className="primary-button" disabled={busy || !previewReady} onClick={() => setConfirmOpen(true)}>
          <GitBranch size={16}/>Sync release/uat
        </button>
      </div>
    </section>

    {preview && <section className="repo-sync-card">
      <div className="repo-sync-section-title">
        <div><GitCompareArrows/><div><h2>{result ? "Sync result" : "Sync preview"}</h2><p>{preview.results.length} repositor{preview.results.length === 1 ? "y" : "ies"} checked.</p></div></div>
      </div>

      <div className="repo-sync-results">
        {preview.results.map((item) => <article key={item.repository} className={`repo-sync-result ${item.error ? "failed" : "ready"}`}>
          <div className="repo-sync-result-head">
            <div>
              <span className="eyebrow">{item.error ? "ACTION REQUIRED" : (item.status || `${item.branch_action || "sync"} branch`).toUpperCase()}</span>
              <h3>{item.repository}</h3>
              <p>SIT source: <strong>{item.reference_repository}:develop</strong></p>
            </div>
            {item.error ? <AlertTriangle size={24}/> : <CheckCircle2 size={24}/>}
          </div>

          {item.error ? <div className="repo-sync-inline error"><span>{item.error}</span></div> : <>
            <div className="repo-sync-branch-summary">
              <span><small>Base</small><strong>develop</strong></span>
              <span>→</span>
              <span><small>{item.branch_action === "update" ? "Update" : "Create"}</small><strong>release/uat</strong></span>
              <span className="repo-sync-file-count">{item.files.filter((file) => file.action !== "unchanged").length} file changes</span>
            </div>

            {item.warnings?.map((warning) => <div className="repo-sync-inline warning" key={warning}><AlertTriangle size={15}/><span>{warning}</span></div>)}

            <div className="repo-sync-file-list">
              {item.files.map((file) => <div key={`${file.source_path}-${file.target_path}`}>
                <span className={`repo-sync-action-tag ${file.action}`}>{file.action}</span>
                <code>{file.source_path}</code>
                <span>→</span>
                <code>{file.target_path}</code>
              </div>)}
            </div>

            {item.message && <div className="repo-sync-inline success"><CheckCircle2 size={16}/><span>{item.message}</span></div>}
            {item.url && <a className="repo-sync-azure-link" href={item.url} target="_blank" rel="noreferrer"><ExternalLink size={15}/>Open release/uat in Azure DevOps</a>}
          </>}
        </article>)}
      </div>
    </section>}

    <PremiumDeploymentModal
      open={confirmOpen}
      variant="warning"
      eyebrow="REPOSITORY WRITE"
      title={`Sync release/uat for ${targets.length} repositor${targets.length === 1 ? "y" : "ies"}?`}
      message="This will create release/uat from develop when missing, or update the existing release/uat branch. Develop is never modified. Only generated UAT configuration files are added or updated."
      details={[
        { label: "Repositories", value: String(targets.length) },
        { label: "Base branch", value: "develop" },
        { label: "Target branch", value: "release/uat" },
        { label: "SIT source", value: referenceRepository.trim() || "Each target repository" },
      ]}
      primaryLabel="Sync release/uat"
      secondaryLabel="Cancel"
      busy={busy}
      onPrimary={() => void executeSync()}
      onSecondary={() => setConfirmOpen(false)}
    />
  </div>;
}
