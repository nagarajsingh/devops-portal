import { useMemo, useState } from "react";
import { BarChart3, Boxes, ClipboardList, FileUp, Home, LogOut, Menu, Search, ShieldCheck } from "lucide-react";
import type { AuthSession, NavItem, PageKey } from "./types";
import LoginPage from "./pages/LoginPage";
import HomePage from "./pages/HomePage";
import DashboardPage from "./pages/DashboardPage";
import RequestsPage from "./pages/RequestsPage";
import FilePlacementPage from "./pages/FilePlacementPage";
import MonitoringPage from "./pages/MonitoringPage";
import MsPortalPage from "./pages/MsPortalPage";
import AdminPage from "./pages/AdminPage";
import NotificationCenter from "./components/NotificationCenter";

const navItems: NavItem[] = [
  { key: "home", label: "Home" },
  { key: "dashboard", label: "Dashboard" },
  { key: "ms-portal", label: "New Pipeline Request" },
  { key: "requests", label: "Pipeline Requests" },
  { key: "file-placement", label: "File Placement", href: "/devops-portal/file-placement/" },
  { key: "monitoring", label: "Monitoring", devopsOnly: true },
  { key: "admin", label: "Admin", devopsOnly: true },
];

const icons = { home: Home, dashboard: BarChart3, requests: ClipboardList, "file-placement": FileUp, monitoring: Boxes, "ms-portal": Boxes, admin: ShieldCheck };

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(() => { const raw = sessionStorage.getItem("devops-session"); return raw ? JSON.parse(raw) : null; });
  const [page, setPage] = useState<PageKey>("home");
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const visibleItems = useMemo(() => navItems.filter(item => !item.devopsOnly || session?.role === "devops"), [session]);
  const filteredItems = visibleItems.filter(item => item.label.toLowerCase().includes(query.toLowerCase()));

  function completeLogin(next: AuthSession) { sessionStorage.setItem("devops-session", JSON.stringify(next)); setSession(next); setPage("home"); }
  function logout() { sessionStorage.removeItem("devops-session"); setSession(null); }
  function navigate(item: NavItem) { setQuery(""); if (item.href) window.location.assign(item.href); else setPage(item.key); }

  if (!session) return <LoginPage onLogin={completeLogin} />;

  const renderPage = () => ({
    home: <HomePage onNavigate={setPage} />,
    dashboard: <DashboardPage token={session.access_token} role={session.role} refreshKey={refreshKey} />,
    requests: <RequestsPage token={session.access_token} role={session.role} refreshKey={refreshKey} />,
    "file-placement": <FilePlacementPage />,
    monitoring: <MonitoringPage />,
    "ms-portal": <MsPortalPage token={session.access_token} onCreated={() => setRefreshKey(value => value + 1)} />,
    admin: <AdminPage />,
  })[page];

  return <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}><aside className="sidebar"><div className="brand"><div className="brand-mark">M</div><div className="brand-copy"><strong>mashreq</strong><span>NEO CORP</span></div></div><button className="collapse-button" onClick={() => setCollapsed(value => !value)} aria-label="Toggle sidebar"><Menu size={20} /></button><nav>{visibleItems.map(item => { const Icon = icons[item.key]; const active = !item.href && page === item.key; return <button key={item.key} className={active ? "nav-item active" : "nav-item"} onClick={() => navigate(item)}><Icon size={20} /><span>{item.label}</span></button>; })}</nav><div className="sidebar-footer"><div className="user-avatar">{session.username.slice(0, 2).toUpperCase()}</div><div><strong>{session.username}</strong><span>{session.role === "devops" ? "DevOps" : "Developer"}</span></div></div></aside><main className="main-area"><header className="topbar"><div className="search-wrap"><Search size={20} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search tasks, services and requests..." />{query && <div className="search-results">{filteredItems.map(item => <button key={item.key} onClick={() => navigate(item)}>{item.label}</button>)}</div>}</div><div className="topbar-actions"><NotificationCenter token={session.access_token} role={session.role} username={session.username} refreshKey={refreshKey} onOpenRequests={() => setPage("requests")} /><span className="role-badge">{session.role === "devops" ? "DevOps" : "Developer"}</span><button className="icon-button" onClick={logout} aria-label="Sign out"><LogOut size={20} /></button></div></header><div className="content">{renderPage()}</div></main></div>;
}
