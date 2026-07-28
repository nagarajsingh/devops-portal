import { useMemo, useState } from "react";
import {
  BarChart3,
  Bell,
  Boxes,
  ChevronDown,
  FileUp,
  Home,
  Menu,
  Search,
  ShieldCheck,
  UserCircle2,
} from "lucide-react";
import type { NavItem, PageKey, Role } from "./types";
import HomePage from "./pages/HomePage";
import DashboardPage from "./pages/DashboardPage";
import FilePlacementPage from "./pages/FilePlacementPage";
import MonitoringPage from "./pages/MonitoringPage";
import MsPortalPage from "./pages/MsPortalPage";
import AdminPage from "./pages/AdminPage";

const navItems: NavItem[] = [
  { key: "home", label: "Home" },
  { key: "dashboard", label: "Dashboard" },
  {
    key: "file-placement",
    label: "File Placement",
    href: "/devops-portal/file-placement/",
  },
  { key: "monitoring", label: "Monitoring", adminOnly: true },
  {
    key: "ms-portal",
    label: "MS Portal",
    href: "/devops-portal/ms-setup/",
  },
  { key: "admin", label: "Admin", adminOnly: true },
];

const icons = {
  home: Home,
  dashboard: BarChart3,
  "file-placement": FileUp,
  monitoring: Boxes,
  "ms-portal": Boxes,
  admin: ShieldCheck,
};

export default function App() {
  const [role, setRole] = useState<Role>("admin");
  const [page, setPage] = useState<PageKey>("home");
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState(false);

  const visibleItems = useMemo(
    () => navItems.filter((item) => !item.adminOnly || role === "admin"),
    [role],
  );

  const filteredItems = visibleItems.filter((item) =>
    item.label.toLowerCase().includes(query.toLowerCase()),
  );

  const renderPage = () =>
    ({
      home: <HomePage />,
      dashboard: <DashboardPage />,
      "file-placement": <FilePlacementPage />,
      monitoring: <MonitoringPage />,
      "ms-portal": <MsPortalPage />,
      admin: <AdminPage />,
    })[page];

  function navigate(item: NavItem) {
    setQuery("");

    if (item.href) {
      window.location.assign(item.href);
      return;
    }

    setPage(item.key);
  }

  function changeRole(nextRole: Role) {
    setRole(nextRole);

    if (
      nextRole === "developer" &&
      (page === "monitoring" || page === "admin")
    ) {
      setPage("home");
    }
  }

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">M</div>
          <div className="brand-copy">
            <strong>mashreq</strong>
            <span>NEO CORP</span>
          </div>
        </div>

        <button
          className="collapse-button"
          onClick={() => setCollapsed((value) => !value)}
          aria-label="Toggle sidebar"
        >
          <Menu size={20} />
        </button>

        <nav>
          {visibleItems.map((item) => {
            const Icon = icons[item.key];
            const isActive = !item.href && page === item.key;

            return (
              <button
                key={item.key}
                className={isActive ? "nav-item active" : "nav-item"}
                onClick={() => navigate(item)}
              >
                <Icon size={20} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="user-avatar">NU</div>
          <div>
            <strong>Nagaraj</strong>
            <span>{role === "admin" ? "DevOps Admin" : "Developer"}</span>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="search-wrap">
            <Search size={20} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search tasks, services and requests..."
            />

            {query && (
              <div className="search-results">
                {filteredItems.map((item) => (
                  <button key={item.key} onClick={() => navigate(item)}>
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="topbar-actions">
            <button className="icon-button" aria-label="Notifications">
              <Bell size={20} />
            </button>

            <label className="role-switch">
              <UserCircle2 size={20} />
              <select
                value={role}
                onChange={(event) => changeRole(event.target.value as Role)}
              >
                <option value="developer">Developer</option>
                <option value="admin">DevOps Admin</option>
              </select>
              <ChevronDown size={16} />
            </label>
          </div>
        </header>

        <div className="content">{renderPage()}</div>
      </main>
    </div>
  );
}
