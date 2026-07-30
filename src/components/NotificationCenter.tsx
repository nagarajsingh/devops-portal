import { useEffect, useMemo, useRef, useState } from "react";
import { Bell, CheckCheck, CircleAlert, CircleCheck, Clock3, X } from "lucide-react";
import { getPipelineRequests } from "../services/api";
import type { PipelineRequest, Role } from "../types";

interface Props {
  token: string;
  role: Role;
  username: string;
  refreshKey: number;
  onOpenRequests: () => void;
}

interface PortalNotification {
  id: string;
  requestId: string;
  repository: string;
  title: string;
  message: string;
  createdAt: string;
  tone: "success" | "warning" | "danger" | "info";
}

const IMPORTANT_DEVOPS_EVENTS = new Set([
  "Approved by App Owner",
  "Rejected by App Owner",
  "Pending Action",
  "Partially Completed",
  "Provisioning Failed",
  "Completed",
  "Closed by DevOps",
]);

function notificationTone(action: string): PortalNotification["tone"] {
  const value = action.toLowerCase();
  if (value.includes("fail") || value.includes("reject")) return "danger";
  if (value.includes("pending") || value.includes("partial")) return "warning";
  if (value.includes("complete") || value.includes("created") || value.includes("approved") || value.includes("closed")) return "success";
  return "info";
}

function eventTitle(action: string, repository: string): string {
  const labels: Record<string, string> = {
    Submitted: "Request submitted",
    "Approval Email Sent": "Approval email sent",
    "Approved by App Owner": "App owner approved",
    "Rejected by App Owner": "App owner rejected",
    "Modified by DevOps": "Request updated by DevOps",
    "Approved by DevOps": "Provisioning started",
    Completed: "Provisioning completed",
    "Partially Completed": "Provisioning needs attention",
    "Pending Action": "DevOps action required",
    Rejected: "Request rejected",
    "Closed by DevOps": "Ticket closed",
  };
  return `${labels[action] ?? action} · ${repository}`;
}

function buildNotifications(requests: PipelineRequest[], role: Role): PortalNotification[] {
  const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
  return requests
    .flatMap((request) => (request.timeline ?? []).map((event, index) => ({ request, event, index })))
    .filter(({ event }) => {
      const timestamp = Date.parse(event.at);
      if (!Number.isFinite(timestamp) || timestamp < cutoff) return false;
      return role === "developer" || IMPORTANT_DEVOPS_EVENTS.has(event.action) || event.action.toLowerCase().includes("fail");
    })
    .map(({ request, event, index }) => ({
      id: `${request.id}:${event.at}:${event.action}:${index}`,
      requestId: request.id,
      repository: request.repository_name,
      title: eventTitle(event.action, request.repository_name),
      message: event.detail || `${event.action} for ${request.id}`,
      createdAt: event.at,
      tone: notificationTone(event.action),
    }))
    .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))
    .slice(0, 40);
}

export default function NotificationCenter({ token, role, username, refreshKey, onOpenRequests }: Props) {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<PortalNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const storageKey = `devops-portal-notifications-read:${username}:${role}`;
  const [readIds, setReadIds] = useState<Set<string>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem(storageKey) || "[]") as string[]); }
    catch { return new Set(); }
  });

  const load = async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const requests = await getPipelineRequests(token);
      setNotifications(buildNotifications(requests, role));
    } catch {
      // The main pages already surface API failures. Keep the bell non-blocking.
    } finally {
      if (!quiet) setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(true), 30000);
    return () => window.clearInterval(timer);
  }, [token, role, refreshKey]);

  useEffect(() => {
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (open && panelRef.current && !panelRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  const unreadCount = useMemo(() => notifications.filter((item) => !readIds.has(item.id)).length, [notifications, readIds]);

  const persistReadIds = (next: Set<string>) => {
    setReadIds(next);
    localStorage.setItem(storageKey, JSON.stringify(Array.from(next).slice(-300)));
  };

  const markAllRead = () => persistReadIds(new Set([...readIds, ...notifications.map((item) => item.id)]));

  const openNotification = (item: PortalNotification) => {
    persistReadIds(new Set([...readIds, item.id]));
    setOpen(false);
    onOpenRequests();
  };

  const Icon = ({ tone }: { tone: PortalNotification["tone"] }) => {
    if (tone === "success") return <CircleCheck size={18} />;
    if (tone === "danger") return <CircleAlert size={18} />;
    return <Clock3 size={18} />;
  };

  return <div className="notification-center" ref={panelRef}>
    <button className={`icon-button notification-trigger ${open ? "active" : ""}`} onClick={() => setOpen((value) => !value)} aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ""}`}>
      <Bell size={20} />
      {unreadCount > 0 && <span className="notification-badge">{unreadCount > 99 ? "99+" : unreadCount}</span>}
    </button>
    {open && <aside className="notification-panel">
      <div className="notification-panel-header">
        <div><span className="eyebrow">ACTIVITY</span><h3>Notifications</h3><p>{unreadCount ? `${unreadCount} unread update${unreadCount === 1 ? "" : "s"}` : "You are all caught up"}</p></div>
        <button className="notification-close" onClick={() => setOpen(false)} aria-label="Close notifications"><X size={18} /></button>
      </div>
      <div className="notification-toolbar">
        <button onClick={markAllRead} disabled={!unreadCount}><CheckCheck size={16} /> Mark all read</button>
        <button onClick={() => void load()} disabled={loading}>{loading ? "Refreshing..." : "Refresh"}</button>
      </div>
      <div className="notification-list">
        {loading && notifications.length === 0 ? <div className="notification-empty">Loading notifications...</div> : notifications.length === 0 ? <div className="notification-empty"><Bell size={24}/><strong>No notifications yet</strong><span>Important onboarding updates will appear here.</span></div> : notifications.map((item) => <button key={item.id} className={`notification-item ${item.tone} ${readIds.has(item.id) ? "read" : "unread"}`} onClick={() => openNotification(item)}>
          <span className="notification-icon"><Icon tone={item.tone} /></span>
          <span className="notification-copy"><strong>{item.title}</strong><span>{item.message}</span><small>{item.requestId} · {new Date(item.createdAt).toLocaleString()}</small></span>
          {!readIds.has(item.id) && <span className="notification-unread-dot" />}
        </button>)}
      </div>
      <button className="notification-footer" onClick={() => { setOpen(false); onOpenRequests(); }}>View all pipeline requests</button>
    </aside>}
  </div>;
}
