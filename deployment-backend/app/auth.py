from __future__ import annotations

import jwt
from fastapi import Depends, Header, HTTPException

from .config import JWT_ALGORITHM, JWT_SECRET
from .logging_config import get_logger
from .models import UserContext

logger = get_logger("auth")


def current_user(authorization: str | None = Header(default=None)) -> UserContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(
            authorization.removeprefix("Bearer ").strip(),
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
        return UserContext(username=payload["sub"], role=payload["role"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        logger.warning("Invalid or expired authentication token")
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def require_devops(user: UserContext = Depends(current_user)) -> UserContext:
    if user.role != "devops":
        raise HTTPException(status_code=403, detail="DevOps access required")
    return user
