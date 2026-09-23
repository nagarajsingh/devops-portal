import { useEffect,useMemo,useState } from "react";
import { BarChart3,Boxes,ClipboardList,FileUp,GitCompareArrows,Home,ListTodo,LogOut,Menu,Rocket,Search,ShieldCheck,UserRound } from "lucide-react";
import type {AuthSession,NavItem,PageKey} from "./types";
import LoginPage from "./pages/LoginPage";
import HomePage from "./pages/HomePage";
import DashboardPage from "./pages/DashboardPage";
import RequestsPage from "./pages/RequestsPage";
import FilePlacementPage from "./pages/FilePlacementPage";
import MonitoringPage from "./pages/MonitoringPage";
import DeploymentManagementPage from "./pages/DeploymentManagementPage";
import MsPortalPage from "./pages/MsPortalPage";
import AdminPage from "./pages/AdminPage";
import DevOpsTasksPage from "./pages/DevOpsTasksPage";
import RepoSyncPage from "./pages/RepoSyncPage";
import ProfilePage from "./pages/ProfilePage";
import NotificationCenter from "./components/NotificationCenter";

const BASE_PATH="/devops-portal";
const PAT_SESSION_KEY="devops-portal-azure-pat";
const DEVOPS_ONLY_PAGES=new Set<PageKey>(["devops-tasks","monitoring","repo-sync"]);

const navItems:NavItem[]=[
 {key:"home",label:"Home"},
 {key:"dashboard",label:"Dashboard"},
 {key:"ms-portal",label:"New Pipeline Request"},
 {key:"requests",label:"Pipeline Requests"},
 {key:"deployment-management",label:"Deployment Management"},
 {key:"repo-sync",label:"SIT → UAT Repo Sync",devopsOnly:true},
 {key:"devops-tasks",label:"DevOps Tasks",devopsOnly:true},
 {key:"file-placement",label:"File Placement"},
 {key:"monitoring",label:"Monitoring",devopsOnly:true},
 {key:"profile",label:"My Profile"},
 {key:"admin",label:"Admin",devopsOnly:true,adminOnly:true}
];

const icons={
 home:Home,
 dashboard:BarChart3,
 requests:ClipboardList,
 "file-placement":FileUp,
 monitoring:Boxes,
 "deployment-management":Rocket,
 "ms-portal":Boxes,
 "devops-tasks":ListTodo,
 "repo-sync":GitCompareArrows,
 profile:UserRound,
 admin:ShieldCheck
};

const pagePaths:Record<PageKey,string>={
 home:`${BASE_PATH}/home`,
 dashboard:`${BASE_PATH}/dashboard`,
 requests:`${BASE_PATH}/requests`,
 "file-placement":`${BASE_PATH}/file-placement`,
 monitoring:`${BASE_PATH}/monitoring`,
 "deployment-management":`${BASE_PATH}/deployment-management`,
 "ms-portal":`${BASE_PATH}/request/new`,
 "devops-tasks":`${BASE_PATH}/devops-tasks`,
 "repo-sync":`${BASE_PATH}/repo-sync`,
 profile:`${BASE_PATH}/profile`,
 admin:`${BASE_PATH}/admin`
};

function pageFromPath(p:string):PageKey{
 const n=p.replace(/\/+$/,"")||"/";
 for(const [k,v] of Object.entries(pagePaths))if(n===v.replace(/\/+$/,""))return k as PageKey;
 return "home";
}

function readStoredSession():AuthSession|null{
 const raw=sessionStorage.getItem("devops-session");
 if(!raw)return null;
 try{return JSON.parse(raw)}
 catch{sessionStorage.removeItem("devops-session");return null;}
}

function pageAllowed(page:PageKey,session:AuthSession|null){
 if(!session)return false;
 if(page==="admin")return session.role==="devops"&&session.is_admin;
 if(DEVOPS_ONLY_PAGES.has(page))return session.role==="devops";
 return true;
}

export default function App(){
 const[session,setSession]=useState<AuthSession|null>(readStoredSession);
 const[page,setPage]=useState<PageKey>(()=>pageFromPath(window.location.pathname));
 const[query,setQuery]=useState("");
 const[collapsed,setCollapsed]=useState(false);
 const[refreshKey,setRefreshKey]=useState(0);

 const visibleItems=useMemo(()=>navItems.filter(i=>(!i.devopsOnly||session?.role==="devops")&&(!i.adminOnly||session?.is_admin)),[session]);
 const filteredItems=visibleItems.filter(i=>i.label.toLowerCase().includes(query.toLowerCase()));

 useEffect(()=>{
  const h=()=>{
   if(!session){window.history.replaceState({},"",`${BASE_PATH}/login`);return;}
   const next=pageFromPath(window.location.pathname);
   setPage(pageAllowed(next,session)?next:"home");
  };
  window.addEventListener("popstate",h);
  return()=>window.removeEventListener("popstate",h);
 },[session]);

 useEffect(()=>{
  if(!session){
   if(window.location.pathname!==`${BASE_PATH}/login`)window.history.replaceState({},"",`${BASE_PATH}/login`);
   return;
  }
  if(window.location.pathname===`${BASE_PATH}/login`){
   window.history.replaceState({},"",pagePaths.home);
   setPage("home");
   return;
  }
  if(!pageAllowed(page,session)){
   window.history.replaceState({},"",pagePaths.home);
   setPage("home");
  }
 },[session,page]);

 function completeLogin(s:AuthSession){
  sessionStorage.setItem("devops-session",JSON.stringify(s));
  setSession(s);setPage("home");
  window.history.replaceState({},"",pagePaths.home);
 }

 function logout(){
  sessionStorage.removeItem("devops-session");
  sessionStorage.removeItem(PAT_SESSION_KEY);
  setSession(null);setPage("home");
  window.history.replaceState({},"",`${BASE_PATH}/login`);
 }

 function changePage(p:PageKey){
  if(!pageAllowed(p,session))return;
  setPage(p);
  window.history.pushState({},"",pagePaths[p]);
 }

 function navigate(i:NavItem){
  setQuery("");
  if(i.href){window.location.assign(i.href);return;}
  changePage(i.key);
 }

 if(!session)return <LoginPage onLogin={completeLogin}/>;

 const renderPage=()=>({
  home:<HomePage onNavigate={changePage} role={session.role}/>,
  dashboard:<DashboardPage token={session.access_token} role={session.role} refreshKey={refreshKey}/>,
  requests:<RequestsPage token={session.access_token} role={session.role} refreshKey={refreshKey}/>,
  "file-placement":<FilePlacementPage token={session.access_token} username={session.username}/>,
  monitoring:<MonitoringPage token={session.access_token}/>,
  "deployment-management":<DeploymentManagementPage token={session.access_token} role={session.role} isAdmin={session.is_admin}/>,
  "ms-portal":<MsPortalPage token={session.access_token} onCreated={()=>setRefreshKey(v=>v+1)}/>,
  "devops-tasks":<DevOpsTasksPage token={session.access_token} username={session.username} isAdmin={session.is_admin}/>,
  "repo-sync":<RepoSyncPage token={session.access_token}/>,
  profile:<ProfilePage token={session.access_token} username={session.username} role={session.role} isAdmin={session.is_admin}/>,
  admin:<AdminPage token={session.access_token} username={session.username}/>
 })[page];

 return <div className={`app-shell ${collapsed?"sidebar-collapsed":""}`}>
  <aside className="sidebar">
   <div className="brand"><div className="brand-mark">N</div><div className="brand-copy"><strong>NEO CORP</strong><span>DEVOPS</span></div></div>
   <button className="collapse-button" onClick={()=>setCollapsed(v=>!v)}><Menu size={20}/></button>
   <nav>{visibleItems.map(i=>{const Icon=icons[i.key];return <button key={i.key} className={!i.href&&page===i.key?"nav-item active":"nav-item"} onClick={()=>navigate(i)}><Icon size={20}/><span>{i.label}</span></button>})}</nav>
   <div className="sidebar-footer"><div className="user-avatar">{session.username.slice(0,2).toUpperCase()}</div><div><strong>{session.username}</strong><span>{session.is_admin?"DevOps Admin":session.role==="devops"?"DevOps":"Developer"}</span></div></div>
  </aside>
  <main className="main-area">
   <header className="topbar">
    <div className="search-wrap"><Search size={20}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search tasks, services and requests..."/>{query&&<div className="search-results">{filteredItems.map(i=><button key={i.key} onClick={()=>navigate(i)}>{i.label}</button>)}</div>}</div>
    <div className="topbar-actions"><NotificationCenter token={session.access_token} role={session.role} username={session.username} refreshKey={refreshKey} onOpenRequests={()=>changePage("requests")}/><button className="role-badge" onClick={()=>changePage("profile")} title="Open My Profile">{session.is_admin?"DevOps Admin":session.role==="devops"?"DevOps":"Developer"}</button><button className="icon-button" onClick={logout}><LogOut size={20}/></button></div>
   </header>
   <div className="content">{renderPage()}</div>
  </main>
 </div>;
}
