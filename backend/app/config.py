from __future__ import annotations

import json
import os
from pathlib import Path


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name)
    return default if not value else value.lower() in {"1", "true", "yes", "y", "on"}


JWT_SECRET = env("JWT_SECRET", "change-me-in-secret")
JWT_ALGORITHM = "HS256"
DATA_FILE = Path(env("REQUEST_DATA_FILE", "/data/requests.json"))
NAMESPACE_ALLOWLIST = [item.strip() for item in env("ALLOWED_NAMESPACES", "automation").split(",") if item.strip()]

DEVOPS_USER = env("DEVOPS_USERNAME", "devops")
DEVOPS_PASSWORD = env("DEVOPS_PASSWORD", "devops123")
DEVELOPER_USER = env("DEVELOPER_USERNAME", "developer")
DEVELOPER_PASSWORD = env("DEVELOPER_PASSWORD", "developer123")

AZDO_ORG = env("AZURE_DEVOPS_ORGANIZATION")
AZDO_PROJECT = env("AZURE_DEVOPS_PROJECT")
BOOTSTRAP_BRANCH = env("BOOTSTRAP_BRANCH", "feature/devops") or "feature/devops"

PORTAL_PUBLIC_URL = env("PORTAL_PUBLIC_URL", "http://localhost:8000").rstrip("/")
APPROVAL_TOKEN_HOURS = int(env("APPROVAL_TOKEN_HOURS", "72"))

DEFAULT_APP_OWNERS = {
    "H2H": "Nagarajs@mashreq.com",
    "Native-Mobile": "mujahid@mashreq.com",
    "Collections": "mohanreddy1@mashreq.com",
    "Safenet": "krishnakants@mashreq.com",
}
try:
    APP_OWNER_EMAILS = {**DEFAULT_APP_OWNERS, **json.loads(env("APP_OWNER_EMAILS", "{}"))}
except json.JSONDecodeError:
    APP_OWNER_EMAILS = DEFAULT_APP_OWNERS

LANGUAGE_PORTS = {
    "java-maven": 8080,
    "node": 3000,
    "python": 8000,
    "container": 8080,
}

SMTP_HOST = env("SMTP_HOST")
SMTP_PORT = int(env("SMTP_PORT", "25"))
SMTP_USERNAME = env("SMTP_USERNAME")
SMTP_PASSWORD = env("SMTP_PASSWORD")
SMTP_STARTTLS = env_bool("SMTP_STARTTLS", False)
SMTP_SSL = env_bool("SMTP_SSL", False)
SMTP_TIMEOUT_SECONDS = int(env("SMTP_TIMEOUT_SECONDS", "30"))
MAIL_FROM = env("MAIL_FROM") or env("MASHREQ_EMAIL_FROM") or SMTP_USERNAME
MAIL_BCC = env("MAIL_BCC") or env("MASHREQ_EMAIL_BCC")

POWER_AUTOMATE_APPROVAL_ENABLED = env_bool("POWER_AUTOMATE_APPROVAL_ENABLED", False)
POWER_AUTOMATE_APPROVAL_URL = env("POWER_AUTOMATE_APPROVAL_URL")
POWER_AUTOMATE_CALLBACK_TOKEN = env("POWER_AUTOMATE_CALLBACK_TOKEN")
POWER_AUTOMATE_TIMEOUT_SECONDS = int(env("POWER_AUTOMATE_TIMEOUT_SECONDS", "30"))
POWER_AUTOMATE_CALLBACK_URL = f"{PORTAL_PUBLIC_URL}/api/app-owner/power-automate-callback"
