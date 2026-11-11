import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Box,
  CheckCircle2,
  Clock3,
  Download,
  FileJson,
  FileText,
  RefreshCw,
  Search,
  Server,
  Settings2,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
import type { Role } from "../../types";
import {
  downloadPodLogs,
  getLogAccess,
  getLogClusters,
  getLogNamespaces,
  getLogPods,
  getManageableLogNamespaces,
  getPodLogs,
  updateLogAccess,
} from "./api";
import type {
  KubernetesLogCluster,
  KubernetesLogPod,
  LogOutputFormat,
  LogWindow,
} from "./types";

interface Props {
  token: string;
  role: Role;
}

const WINDOWS: { value: LogWindow; label: string }[] = [
  { value: "live", label: "Live" },
  { value: "5m", label: "5 mins" },
  { value: "10m", label: "10 mins" },
  { value: "30m", label: "30 mins" },
  { value: "1h", label: "1 hour" },
  { value: "5h", label: "5 hours" },
  { value: "12h", label: "12 hours" },
  { value: "24h", label: "24 hours" },
  { value: "3d", label: "3 days" },
  { value: "7d", label: "7 days" },
];

function phaseClass(phase: string) {
  const value = phase.toLowerCase();
  if (value === "running" || value === "succeeded") return "healthy";
  if (value === "pending") return "warning";
  return "danger-status";
}

function formatDate(value?: string | null) {
  if (!value) return "Unknown";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export default function KubernetesLogsPage({ token, role }: Props) {
  const [clusters, setClusters] = useState<KubernetesLogCluster[]>([]);
  const [cluster, setCluster] = useState("");
  const [namespaces, setNamespaces] = useState<string[]>([]);
  const [namespace, setNamespace] = useState("");
  const [pods, setPods] = useState<KubernetesLogPod[]>([]);
  const [podName, setPodName] = useState("");
  const [container, setContainer] = useState("");
  const [windowValue, setWindowValue] = useState<LogWindow>("live");
  const [outputFormat, setOutputFormat] = useState<LogOutputFormat>("standard");
  const [includePrevious, setIncludePrevious] = useState(true);
  const [podSearch, setPodSearch] = useState("");
  const [logContent, setLogContent] = useState("");
  const [logMeta, setLogMeta] = useState({ lines: 0, fetchedAt: "", truncated: false, source: "" });
  const [loadingClusters, setLoadingClusters] = useState(true);
  const [loadingPods, setLoadingPods] = useState(false);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);

  const [manageOpen, setManageOpen] = useState(false);
  const [manageCluster, setManageCluster] = useState("");
  const [manageableNamespaces, setManageableNamespaces] = useState<string[]>([]);
  const [enabledNamespaces, setEnabledNamespaces] = useState<string[]>([]);
  const [manageSearch, setManageSearch] = useState("");
  const [manageLoading, setManageLoading] = useState(false);
  const [manageSaving, setManageSaving] = useState(false);
  const [manageMessage, setManageMessage] = useState("");

  const logViewerRef = useRef<HTMLPreElement | null>(null);

  const loadClusters = useCallback(async () => {
    setLoadingClusters(true);
    setError("");
    try {
      const rows = await getLogClusters(token);
      setClusters(rows);
      setCluster((current) => current || rows[0]?.name || "");
      setManageCluster((current) => current || rows[0]?.name || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load Kubernetes clusters");
    } finally {
      setLoadingClusters(false);
    }
  }, [token]);

  useEffect(() => { void loadClusters(); }, [loadClusters]);

  useEffect(() => {
    setNamespaces([]);
    setNamespace("");
    setPods([]);
    setPodName("");
    setContainer("");
    setLogContent("");
    if (!cluster) return;
    getLogNamespaces(cluster, token)
      .then((rows) => {
        setNamespaces(rows);
        setNamespace(rows[0] || "");
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load namespaces"));
  }, [cluster, token]);

  const loadPods = useCallback(async () => {
    if (!cluster || !namespace) {
      setPods([]);
      return;
    }
    setLoadingPods(true);
    setError("");
    try {
      const rows = await getLogPods(cluster, namespace, token);
      setPods(rows);
      setPodName((current) => rows.some((item) => item.name === current) ? current : rows[0]?.name || "");
    } catch (reason) {
      setPods([]);
      setPodName("");
      setError(reason instanceof Error ? reason.message : "Unable to load pods");
    } finally {
      setLoadingPods(false);
    }
  }, [cluster, namespace, token]);

  useEffect(() => { void loadPods(); }, [loadPods]);

  const selectedPod = useMemo(
    () => pods.find((item) => item.name === podName),
    [pods, podName],
  );

  useEffect(() => {
    const containers = selectedPod?.containers || [];
    setContainer((current) => containers.includes(current) ? current : containers[0] || "");
  }, [selectedPod]);

  const loadLogs = useCallback(async (silent = false) => {
    if (!cluster || !namespace || !podName || !container) return;
    if (!silent) setLoadingLogs(true);
    if (!silent) setError("");
    try {
      const result = await getPodLogs(
        cluster,
        namespace,
        podName,
        container,
        windowValue,
        outputFormat,
        includePrevious,
        token,
      );
      setLogContent(result.content);
      setLogMeta({
        lines: result.line_count,
        fetchedAt: result.fetched_at,
        truncated: result.truncated,
        source: result.source,
      });
    } catch (reason) {
      if (!silent) setError(reason instanceof Error ? reason.message : "Unable to load pod logs");
    } finally {
      if (!silent) setLoadingLogs(false);
    }
  }, [cluster, namespace, podName, container, windowValue, outputFormat, includePrevious, token]);

  useEffect(() => {
    if (!container) {
      setLogContent("");
      return;
    }
    void loadLogs();
  }, [container, windowValue, outputFormat, includePrevious, loadLogs]);

  useEffect(() => {
    if (windowValue !== "live" || !container) return;
    const timer = window.setInterval(() => void loadLogs(true), 3000);
    return () => window.clearInterval(timer);
  }, [windowValue, container, loadLogs]);

  useEffect(() => {
    if (!autoScroll || !logViewerRef.current) return;
    logViewerRef.current.scrollTop = logViewerRef.current.scrollHeight;
  }, [logContent, autoScroll]);

  useEffect(() => {
    if (!manageOpen || role !== "devops" || !manageCluster) return;
    setManageLoading(true);
    setManageMessage("");
    Promise.all([
      getManageableLogNamespaces(manageCluster, token),
      getLogAccess(token),
    ])
      .then(([available, access]) => {
        setManageableNamespaces(available);
        setEnabledNamespaces(access.clusters[manageCluster] || []);
      })
      .catch((reason) => setManageMessage(reason instanceof Error ? reason.message : "Unable to load namespace access"))
      .finally(() => setManageLoading(false));
  }, [manageOpen, manageCluster, role, token]);

  const filteredPods = useMemo(() => {
    const query = podSearch.trim().toLowerCase();
    return query ? pods.filter((item) => item.name.toLowerCase().includes(query)) : pods;
  }, [pods, podSearch]);

  const filteredManageNamespaces = useMemo(() => {
    const query = manageSearch.trim().toLowerCase();
    return query ? manageableNamespaces.filter((item) => item.toLowerCase().includes(query)) : manageableNamespaces;
  }, [manageableNamespaces, manageSearch]);

  async function saveNamespaceAccess() {
    if (!manageCluster) return;
    setManageSaving(true);
    setManageMessage("");
    try {
      await updateLogAccess(manageCluster, enabledNamespaces, token);
      setManageMessage(`Saved ${enabledNamespaces.length} enabled namespace${enabledNamespaces.length === 1 ? "" : "s"} for ${manageCluster}.`);
      await loadClusters();
      if (cluster === manageCluster) {
        const rows = await getLogNamespaces(cluster, token);
        setNamespaces(rows);
        if (!rows.includes(namespace)) setNamespace(rows[0] || "");
      }
    } catch (reason) {
      setManageMessage(reason instanceof Error ? reason.message : "Unable to save namespace access");
    } finally {
      setManageSaving(false);
    }
  }

  async function downloadLogs() {
    if (!cluster || !namespace || !podName || !container) return;
    setDownloading(true);
    setError("");
    try {
      await downloadPodLogs(
        cluster,
        namespace,
        podName,
        container,
        windowValue,
        outputFormat,
        includePrevious,
        token,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to download logs");
    } finally {
      setDownloading(false);
    }
  }

  return <section className="klog-page">
    <div className="klog-hero">
      <div>
        <span className="eyebrow">KUBERNETES OBSERVABILITY</span>
        <h1>Cluster Logs</h1>
        <p>Live and historical pod logs across approved namespaces and Kubernetes clusters.</p>
      </div>
      <div className="klog-hero-actions">
        <div className="klog-live-badge"><Activity size={16}/><span>{windowValue === "live" ? "Live refresh" : "Historical view"}</span></div>
        {role === "devops" && <button className="secondary-button" onClick={() => setManageOpen((value) => !value)}><ShieldCheck size={17}/>{manageOpen ? "Close access manager" : "Manage namespace access"}</button>}
      </div>
    </div>

    {role === "devops" && manageOpen && <article className="klog-access-panel">
      <div className="klog-access-heading">
        <div><span className="eyebrow">DEVOPS CONTROL</span><h3>Namespace log access</h3><p>Only enabled namespaces are visible in the log viewer for Developers and DevOps.</p></div>
        <Settings2 size={24}/>
      </div>
      <div className="klog-access-controls">
        <label>Cluster<select value={manageCluster} onChange={(event) => setManageCluster(event.target.value)}>{clusters.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
        <label className="klog-search-field"><span>Find namespace</span><div><Search size={16}/><input value={manageSearch} onChange={(event) => setManageSearch(event.target.value)} placeholder="Search namespaces..."/></div></label>
        <div className="klog-bulk-actions"><button className="secondary-button" onClick={() => setEnabledNamespaces(manageableNamespaces)}>Enable all</button><button className="secondary-button" onClick={() => setEnabledNamespaces([])}>Clear all</button></div>
      </div>
      {manageLoading ? <div className="klog-empty">Loading namespace inventory...</div> : <div className="klog-namespace-grid">
        {filteredManageNamespaces.map((item) => {
          const checked = enabledNamespaces.includes(item);
          return <label className={checked ? "enabled" : ""} key={item}><input type="checkbox" checked={checked} onChange={(event) => setEnabledNamespaces((current) => event.target.checked ? [...current, item].sort() : current.filter((value) => value !== item))}/><span>{item}</span><small>{checked ? "Portal logs enabled" : "Restricted"}</small></label>;
        })}
      </div>}
      <div className="klog-access-footer"><span>{enabledNamespaces.length} of {manageableNamespaces.length} enabled</span><div>{manageMessage && <small>{manageMessage}</small>}<button className="primary-button" disabled={manageSaving} onClick={() => void saveNamespaceAccess()}>{manageSaving ? "Saving..." : "Save access"}</button></div></div>
    </article>}

    {error && <div className="form-error">{error}</div>}

    <div className="klog-selector-bar">
      <label><span><Server size={15}/>Cluster</span><select disabled={loadingClusters} value={cluster} onChange={(event) => setCluster(event.target.value)}><option value="">Select cluster</option>{clusters.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
      <label><span><ShieldCheck size={15}/>Namespace</span><select disabled={!cluster || namespaces.length === 0} value={namespace} onChange={(event) => setNamespace(event.target.value)}><option value="">{namespaces.length ? "Select namespace" : "No enabled namespaces"}</option>{namespaces.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <label><span><Clock3 size={15}/>Time window</span><select value={windowValue} onChange={(event) => setWindowValue(event.target.value as LogWindow)}>{WINDOWS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label><span><FileText size={15}/>Format</span><select value={outputFormat} onChange={(event) => setOutputFormat(event.target.value as LogOutputFormat)}><option value="standard">Standard logs</option><option value="text">Text</option><option value="json">JSON</option></select></label>
    </div>

    <div className="klog-workspace">
      <aside className="klog-pod-panel">
        <div className="klog-panel-heading">
          <div><span className="eyebrow">WORKLOADS</span><h3>Pods</h3></div>
          <button className="klog-icon-button" disabled={!namespace || loadingPods} title="Refresh pods" onClick={() => void loadPods()}><RefreshCw size={16} className={loadingPods ? "spin" : ""}/></button>
        </div>
        <div className="klog-pod-search"><Search size={16}/><input value={podSearch} onChange={(event) => setPodSearch(event.target.value)} placeholder="Filter pods..."/></div>
        <div className="klog-pod-list">
          {!namespace ? <div className="klog-empty"><ShieldCheck size={22}/><span>Select an enabled namespace</span></div> : loadingPods && pods.length === 0 ? <div className="klog-empty">Loading pods...</div> : filteredPods.length === 0 ? <div className="klog-empty">No pods found</div> : filteredPods.map((pod) => <button key={pod.name} className={podName === pod.name ? "selected" : ""} onClick={() => setPodName(pod.name)}><div><Box size={16}/><strong>{pod.name}</strong></div><div><span className={`status ${phaseClass(pod.phase)}`}>{pod.phase}</span><small>{pod.restarts} restart{pod.restarts === 1 ? "" : "s"}</small></div><small>{formatDate(pod.created_at)}</small></button>)}
        </div>
      </aside>

      <main className="klog-console-panel">
        <div className="klog-console-heading">
          <div>
            <span className="eyebrow">LOG STREAM</span>
            <h3>{podName || "Select a pod"}</h3>
            {selectedPod && <p>{selectedPod.phase} · {selectedPod.node || "node unavailable"} · created {formatDate(selectedPod.created_at)}</p>}
          </div>
          <div className="klog-console-actions">
            <label className="klog-container-select"><span>Container</span><select value={container} disabled={!selectedPod} onChange={(event) => setContainer(event.target.value)}><option value="">Select container</option>{(selectedPod?.containers || []).map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <button className="secondary-button" disabled={!container || loadingLogs} onClick={() => void loadLogs()}><RefreshCw size={16} className={loadingLogs ? "spin" : ""}/>{loadingLogs ? "Loading..." : "Refresh"}</button>
            <button className="primary-button" disabled={!container || downloading} onClick={() => void downloadLogs()}><Download size={16}/>{downloading ? "Preparing..." : "Download"}</button>
          </div>
        </div>

        <div className="klog-console-toolbar">
          <div className="klog-format-chip">{outputFormat === "json" ? <FileJson size={15}/> : <TerminalSquare size={15}/>}<span>{outputFormat.toUpperCase()}</span></div>
          <label><input type="checkbox" checked={includePrevious} onChange={(event) => setIncludePrevious(event.target.checked)}/>Include previous container instance</label>
          <label><input type="checkbox" checked={autoScroll} onChange={(event) => setAutoScroll(event.target.checked)}/>Auto-scroll</label>
          <div className="klog-console-meta"><span>{logMeta.lines} lines</span>{logMeta.fetchedAt && <span>Updated {new Date(logMeta.fetchedAt).toLocaleTimeString()}</span>}<span>{logMeta.source || "—"}</span></div>
        </div>

        <div className="klog-console-shell">
          {windowValue === "live" && <div className="klog-live-strip"><span/>LIVE · refreshes every 3 seconds</div>}
          {logMeta.truncated && <div className="klog-truncated">Output exceeded the portal response limit. Showing the newest available content.</div>}
          {!container ? <div className="klog-console-empty"><TerminalSquare size={34}/><strong>Select a pod and container</strong><span>Logs will load automatically.</span></div> : loadingLogs && !logContent ? <div className="klog-console-empty">Loading logs...</div> : <pre ref={logViewerRef}>{logContent || "No log lines were returned for this time window."}</pre>}
        </div>

        <div className="klog-history-note">
          <CheckCircle2 size={16}/>
          <span>Historical windows include logs from retained Running/Succeeded/Failed pods and the previous container instance when Kubernetes still has it. Logs from pods already deleted by Kubernetes require a centralized log store such as Splunk.</span>
        </div>
      </main>
    </div>
  </section>;
}
