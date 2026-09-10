import { DragEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, FileUp, Server, ShieldCheck, UploadCloud } from "lucide-react";
import {
  getFilePlacementAudit,
  getFilePlacementNamespaces,
  getFilePlacementPods,
  uploadFilePlacement,
  type FilePlacementAudit,
  type FilePlacementPod,
} from "../services/api";
import "../file-placement.css";

const MAX_FILE_SIZE = 200 * 1024 * 1024;

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function FilePlacementPage({ token, username }: { token: string; username: string }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [namespaces, setNamespaces] = useState<string[]>([]);
  const [namespace, setNamespace] = useState("");
  const [pods, setPods] = useState<FilePlacementPod[]>([]);
  const [podName, setPodName] = useState("");
  const [containerName, setContainerName] = useState("");
  const [destinationPath, setDestinationPath] = useState("/tmp/sample.txt");
  const [audit, setAudit] = useState<FilePlacementAudit[]>([]);
  const [loadingPods, setLoadingPods] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const selectedPod = useMemo(() => pods.find((pod) => pod.name === podName), [pods, podName]);

  useEffect(() => {
    void (async () => {
      try {
        const [items, history] = await Promise.all([
          getFilePlacementNamespaces(token),
          getFilePlacementAudit(token),
        ]);
        setNamespaces(items);
        setAudit(history);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Unable to load file placement data");
      }
    })();
  }, [token]);

  useEffect(() => {
    setPods([]);
    setPodName("");
    setContainerName("");
    if (!namespace) return;
    setLoadingPods(true);
    void getFilePlacementPods(namespace, token)
      .then((items) => setPods(items))
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load pods"))
      .finally(() => setLoadingPods(false));
  }, [namespace, token]);

  useEffect(() => {
    const firstContainer = selectedPod?.containers?.[0] ?? "";
    if (!selectedPod?.containers.includes(containerName)) setContainerName(firstContainer);
  }, [selectedPod, containerName]);

  function chooseFile(next: File | null) {
    setError("");
    setSuccess("");
    if (!next) return;
    if (next.size > MAX_FILE_SIZE) {
      setFile(null);
      setError("Maximum file size is 200 MB");
      return;
    }
    setFile(next);
    if (destinationPath === "/tmp/sample.txt" || !destinationPath.trim()) {
      setDestinationPath(`/tmp/${next.name}`);
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files?.[0] ?? null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    if (!file || !namespace || !podName || !destinationPath.trim()) {
      setError("Select a file, namespace, pod and destination path");
      return;
    }
    try {
      setUploading(true);
      const result = await uploadFilePlacement(
        { file, namespace, podName, containerName, destinationPath },
        token,
      );
      setSuccess(`${file.name} placed successfully in ${namespace}/${podName}:${destinationPath}`);
      setAudit((current) => [result, ...current].slice(0, 25));
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "File placement failed");
      try { setAudit(await getFilePlacementAudit(token)); } catch { /* keep current audit */ }
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="fp-page">
      <div className="fp-heading">
        <div>
          <span className="eyebrow">INTERNAL DEVOPS UTILITY</span>
          <h2>File Placement</h2>
          <p>Securely upload and place files inside Kubernetes pods</p>
        </div>
        <div className="fp-connected"><CheckCircle2 size={17} /> Kubernetes connected</div>
      </div>

      {error && <div className="form-error">{error}</div>}
      {success && <div className="fp-success"><CheckCircle2 size={18} /> {success}</div>}

      <form className="fp-grid" onSubmit={submit}>
        <div className="fp-card">
          <div className="fp-card-title"><FileUp size={21} /><div><h3>Upload File</h3><p>Choose a file from your machine and place it directly inside the selected pod.</p></div></div>
          <div
            className={`fp-dropzone ${dragging ? "dragging" : ""}`}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
          >
            <input ref={inputRef} type="file" hidden onChange={(event) => chooseFile(event.target.files?.[0] ?? null)} />
            <div className="fp-upload-icon"><UploadCloud size={34} /></div>
            {file ? (
              <><strong>{file.name}</strong><span>{formatBytes(file.size)}</span><small>Click or drop another file to replace</small></>
            ) : (
              <><strong>Drag and drop file here</strong><span>or click to browse from your machine</span><small>Limit 200MB per file</small></>
            )}
          </div>
          <div className="fp-limit"><ShieldCheck size={16} /><span><strong>Maximum file size: 200 MB</strong><br />The uploaded file is streamed to the selected pod. The portal stores audit metadata, not the file contents.</span></div>
        </div>

        <div className="fp-card">
          <div className="fp-card-title"><Server size={21} /><div><h3>Placement Details</h3><p>Select the namespace and pod, then enter the exact absolute destination path.</p></div></div>
          <div className="fp-fields">
            <label>Namespace<select value={namespace} onChange={(event) => setNamespace(event.target.value)} required><option value="">Select namespace</option>{namespaces.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label>Pod<select value={podName} onChange={(event) => setPodName(event.target.value)} required disabled={!namespace || loadingPods}><option value="">{loadingPods ? "Loading pods..." : "Select pod"}</option>{pods.map((pod) => <option key={pod.name} value={pod.name}>{pod.name}</option>)}</select></label>
            {selectedPod && selectedPod.containers.length > 1 && <label>Container<select value={containerName} onChange={(event) => setContainerName(event.target.value)}>{selectedPod.containers.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>}
            <label>Destination Path<input value={destinationPath} onChange={(event) => setDestinationPath(event.target.value)} placeholder="/tmp/sample.txt" required /></label>
          </div>
          <div className="fp-path-preview"><span>Target path</span><code>{destinationPath || "/tmp/sample.txt"}</code></div>
          <div className="fp-user-note">Placement will be recorded against <strong>{username}</strong>.</div>
          <button className="primary-button fp-submit" disabled={uploading || !file || !namespace || !podName}>{uploading ? "Placing file..." : "Place File"}</button>
        </div>
      </form>

      <div className="fp-audit-card">
        <div className="fp-audit-heading"><div><span className="eyebrow">AUDIT TRAIL</span><h3>Recent File Placements</h3></div><button className="secondary-button" onClick={async () => setAudit(await getFilePlacementAudit(token))}>Refresh</button></div>
        <div className="fp-table-wrap">
          <table>
            <thead><tr><th>User</th><th>File</th><th>Namespace / Pod</th><th>Destination</th><th>Size</th><th>Status</th><th>Time</th></tr></thead>
            <tbody>{audit.length === 0 ? <tr><td colSpan={7} className="fp-empty">No file placements recorded yet.</td></tr> : audit.map((item) => <tr key={item.id}><td>{item.user_email}</td><td>{item.file_name}</td><td><strong>{item.namespace}</strong><small>{item.pod_name}{item.container_name ? ` / ${item.container_name}` : ""}</small></td><td><code>{item.destination_path}</code></td><td>{formatBytes(item.file_size)}</td><td><span className={`fp-status ${item.status.toLowerCase()}`}>{item.status}</span></td><td>{new Date(item.created_at).toLocaleString()}</td></tr>)}</tbody>
          </table>
        </div>
      </div>

      <footer className="fp-footer">Mashreq NEO CORP · Internal DevOps File Placement</footer>
    </section>
  );
}
