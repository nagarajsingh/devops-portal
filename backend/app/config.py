from __future__ import annotations

import os
from pathlib import Path

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-secret")
JWT_ALGORITHM = "HS256"
DATA_FILE = Path(os.getenv("REQUEST_DATA_FILE", "/data/requests.json"))
NAMESPACE_ALLOWLIST = [
    item.strip()
    for item in os.getenv("ALLOWED_NAMESPACES", "automation").split(",")
    if item.strip()
]

DEVOPS_USER = os.getenv("DEVOPS_USERNAME", "devops")
DEVOPS_PASSWORD = os.getenv("DEVOPS_PASSWORD", "devops123")
DEVELOPER_USER = os.getenv("DEVELOPER_USERNAME", "developer")
DEVELOPER_PASSWORD = os.getenv("DEVELOPER_PASSWORD", "developer123")

AZDO_ORG = os.getenv("AZURE_DEVOPS_ORGANIZATION", "").strip()
AZDO_PROJECT = os.getenv("AZURE_DEVOPS_PROJECT", "").strip()
AZDO_PAT = os.getenv("AZURE_DEVOPS_PAT", "").strip()
BOOTSTRAP_BRANCH = os.getenv("BOOTSTRAP_BRANCH", "feature/devops").strip() or "feature/devops"
