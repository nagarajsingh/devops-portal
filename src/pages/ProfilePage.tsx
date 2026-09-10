import { FormEvent, useState } from "react";
import { KeyRound, ShieldCheck, UserRound } from "lucide-react";
import { changePassword } from "../services/api";
import type { Role } from "../types";

export default function ProfilePage({
  token,
  username,
  role,
  isAdmin,
}: {
  token: string;
  username: string;
  role: Role;
  isAdmin: boolean;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    setError("");

    if (newPassword.length < 10) {
      setError("New password must contain at least 10 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation do not match");
      return;
    }
    if (currentPassword === newPassword) {
      setError("New password must be different from your current password");
      return;
    }

    try {
      setBusy(true);
      const result = await changePassword(
        {
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        },
        token,
      );
      setMessage(result.message || "Password updated successfully");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to change password");
    } finally {
      setBusy(false);
    }
  }

  const roleLabel = isAdmin ? "DevOps Admin" : role === "devops" ? "DevOps" : "Developer";

  return (
    <section>
      <div className="section-heading">
        <div>
          <span className="eyebrow">ACCOUNT SETTINGS</span>
          <h2>My Profile</h2>
          <p>View your portal identity and securely update your password.</p>
        </div>
      </div>

      <div className="profile-layout">
        <div className="form-card profile-summary-card">
          <div className="profile-avatar"><UserRound size={30} /></div>
          <div>
            <span className="eyebrow">SIGNED IN AS</span>
            <h3>{username}</h3>
            <div className="profile-role"><ShieldCheck size={16} /> {roleLabel}</div>
          </div>
        </div>

        <form className="form-card profile-password-card" onSubmit={submit}>
          <div className="profile-password-heading">
            <KeyRound size={22} />
            <div>
              <h3>Change Password</h3>
              <p>Enter your existing password before choosing a new one.</p>
            </div>
          </div>

          <label>
            Current Password
            <input
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>

          <label>
            New Password
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              autoComplete="new-password"
              minLength={10}
              maxLength={128}
              required
            />
            <small>Minimum 10 characters.</small>
          </label>

          <label>
            Confirm New Password
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              autoComplete="new-password"
              minLength={10}
              maxLength={128}
              required
            />
          </label>

          {error && <div className="form-error">{error}</div>}
          {message && <div className="form-success">{message}</div>}

          <div>
            <button
              className="primary-button"
              disabled={busy || !currentPassword || !newPassword || !confirmPassword}
            >
              {busy ? "Updating password..." : "Update Password"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
