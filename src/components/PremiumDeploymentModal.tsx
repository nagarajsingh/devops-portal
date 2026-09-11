import { AlertTriangle, CheckCircle2, Info, ShieldAlert, XCircle } from "lucide-react";

export type DeploymentModalVariant = "success" | "warning" | "error" | "info";

interface DetailItem {
  label: string;
  value: string;
}

interface Props {
  open: boolean;
  variant?: DeploymentModalVariant;
  eyebrow?: string;
  title: string;
  message: string;
  details?: DetailItem[];
  primaryLabel?: string;
  secondaryLabel?: string;
  busy?: boolean;
  inputLabel?: string;
  inputValue?: string;
  inputPlaceholder?: string;
  onInputChange?: (value: string) => void;
  onPrimary: () => void;
  onSecondary?: () => void;
}

const icons = {
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
  info: Info,
};

export default function PremiumDeploymentModal({
  open,
  variant = "info",
  eyebrow = "DEVOPS PORTAL",
  title,
  message,
  details = [],
  primaryLabel = "Continue",
  secondaryLabel,
  busy = false,
  inputLabel,
  inputValue = "",
  inputPlaceholder,
  onInputChange,
  onPrimary,
  onSecondary,
}: Props) {
  if (!open) return null;
  const Icon = icons[variant] || ShieldAlert;

  return (
    <div className="deployment-modal-backdrop" role="presentation">
      <div className={`deployment-modal-card ${variant}`} role="dialog" aria-modal="true" aria-labelledby="deployment-modal-title">
        <div className="deployment-modal-icon"><Icon size={27} /></div>
        <span className="eyebrow">{eyebrow}</span>
        <h3 id="deployment-modal-title">{title}</h3>
        <p>{message}</p>

        {details.length > 0 && (
          <div className="deployment-modal-details">
            {details.map((item) => (
              <div key={`${item.label}-${item.value}`}>
                <span>{item.label}</span>
                <strong>{item.value || "—"}</strong>
              </div>
            ))}
          </div>
        )}

        {inputLabel && (
          <label className="deployment-modal-input">
            {inputLabel}
            <input
              value={inputValue}
              placeholder={inputPlaceholder}
              onChange={(event) => onInputChange?.(event.target.value)}
              autoFocus
            />
          </label>
        )}

        <div className="deployment-modal-actions">
          {secondaryLabel && onSecondary && (
            <button className="secondary-button" disabled={busy} onClick={onSecondary}>{secondaryLabel}</button>
          )}
          <button className="primary-button" disabled={busy} onClick={onPrimary}>{busy ? "Processing..." : primaryLabel}</button>
        </div>
      </div>
    </div>
  );
}
