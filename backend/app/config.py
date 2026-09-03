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
BOOTSTRAP_BRANCH = env("BOOTSTRAP_BRANCH", "devops/pipeline") or "devops/pipeline"

LOCAL_KUBERNETES_TARGET = env("LOCAL_KUBERNETES_TARGET", "mashreq-titan-non-prod") or "mashreq-titan-non-prod"
DEFAULT_KUBERNETES_TARGETS = [
    LOCAL_KUBERNETES_TARGET,
    "mashreq-nativemob-safenet-nonprod",
    "mashreq-titan-non-prod",
    "mashreqdigicollecteguat",
]
_configured_targets = [
    item.strip()
    for item in env("KUBERNETES_TARGETS", ",".join(DEFAULT_KUBERNETES_TARGETS)).split(",")
    if item.strip()
]
KUBERNETES_TARGETS = list(dict.fromkeys(_configured_targets))
KUBERNETES_PROVISIONING_PIPELINE_ID = int(env("KUBERNETES_PROVISIONING_PIPELINE_ID", "1586"))
KUBERNETES_PROVISIONING_TIMEOUT_SECONDS = int(env("KUBERNETES_PROVISIONING_TIMEOUT_SECONDS", "900"))
KUBERNETES_PROVISIONING_POLL_SECONDS = max(2, int(env("KUBERNETES_PROVISIONING_POLL_SECONDS", "10")))

KUBERNETES_INVENTORY_PIPELINE_ID = int(env("KUBERNETES_INVENTORY_PIPELINE_ID", "0"))
KUBERNETES_INVENTORY_ARTIFACT_NAME = env("KUBERNETES_INVENTORY_ARTIFACT_NAME", "cluster-inventory") or "cluster-inventory"
KUBERNETES_INVENTORY_REFRESH_SECONDS = max(60, int(env("KUBERNETES_INVENTORY_REFRESH_SECONDS", "300")))
KUBERNETES_INVENTORY_FILE = Path(env("KUBERNETES_INVENTORY_FILE", "/data/cluster-inventory.json"))
KUBERNETES_INVENTORY_PAT = env("KUBERNETES_INVENTORY_PAT")

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
