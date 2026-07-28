import { FormEvent, useState } from "react";
import { login } from "../services/api";
import type { AuthSession, Role } from "../types";

interface Props { onLogin: (session: AuthSession) => void; }

export default function LoginPage({ onLogin }: Props) {
  const [role, setRole] = useState<Role>("developer");
  const [username, setUsername] = useState("developer");
  const [password, setPassword] = useState("developer123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function changeRole(next: Role) {
    setRole(next);
    setUsername(next === "devops" ? "devops" : "developer");
    setPassword(next === "devops" ? "devops123" : "developer123");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try { onLogin(await login(username, password, role)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Login failed"); }
    finally { setLoading(false); }
  }

  return <main className="login-page"><form className="login-card" onSubmit={submit}>
    <div className="brand"><div className="brand-mark">M</div><div className="brand-copy"><strong>mashreq</strong><span>DEVOPS PORTAL</span></div></div>
    <h1>Sign in</h1><p>Use the temporary Developer or DevOps account.</p>
    <label>Role<select value={role} onChange={e => changeRole(e.target.value as Role)}><option value="developer">Developer</option><option value="devops">DevOps</option></select></label>
    <label>Username<input value={username} onChange={e => setUsername(e.target.value)} required /></label>
    <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
    {error && <div className="form-error">{error}</div>}
    <button className="primary-button" disabled={loading}>{loading ? "Signing in..." : "Sign in"}</button>
  </form></main>;
}
