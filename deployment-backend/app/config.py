from __future__ import annotations

import os

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-secret").strip()
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256").strip() or "HS256"
AZDO_ORG = os.getenv("AZURE_DEVOPS_ORGANIZATION", "").strip()
AZDO_PROJECT = os.getenv("AZURE_DEVOPS_PROJECT", "").strip()
