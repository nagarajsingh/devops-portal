import { FormEvent, useState } from "react";
import { login } from "../services/api";
import type { AuthSession, Role } from "../types";

interface Props {
  onLogin: (session: AuthSession) => void;
}

export default function LoginPage({ onLogin }: Props) {
  const [role, setRole] = useState<Role>("developer");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      onLogin(await login(username.trim(), password, role));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="brand">
          <div className="brand-mark">N</div>
          <div className="brand-copy">
            <strong>Neocorp DevOps</strong>
            <span>SELF-SERVICE PORTAL</span>
          </div>
        </div>

        <h1>Welcome back</h1>
        <p>Sign in with your authorized portal account.</p>

        <label>
          Role
          <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
            <option value="developer">Developer</option>
            <option value="devops">DevOps</option>
          </select>
        </label>

        <label>
          Username
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            placeholder="Enter your username"
            required
          />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            placeholder="Enter your password"
            required
          />
        </label>

        {error && <div className="form-error">{error}</div>}

        <button className="primary-button" disabled={loading || !username.trim() || !password}>
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}
