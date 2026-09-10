from __future__ import annotations

from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, Header, HTTPException
from .config import JWT_ALGORITHM, JWT_SECRET
from .logging_config import get_logger
from .models import ChangePasswordRequest, LoginRequest, LoginResponse, Role, UserContext
from .user_store import change_user_password, get_user, verify_password

logger = get_logger("auth")

def create_token(username: str, role: Role, is_admin: bool = False) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "role": role, "is_admin": is_admin, "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=8)).timestamp())}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def authenticate(payload: LoginRequest) -> LoginResponse:
    email = payload.username.strip().lower()
    if not email.endswith("@mashreq.com"):
        raise HTTPException(status_code=401, detail="User ID must use @mashreq.com")
    try:
        user = get_user(email)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    valid = bool(user and user.is_active and verify_password(payload.password, user.password_hash))
    if not valid:
        logger.warning("Login failed username=%s", email)
        raise HTTPException(status_code=401, detail="Invalid credentials or inactive account")
    logger.info("Login successful username=%s role=%s admin=%s", email, user.role, user.is_admin)
    return LoginResponse(access_token=create_token(email, user.role, user.is_admin), username=email, role=user.role, is_admin=user.is_admin)

def current_user(authorization: str | None = Header(default=None)) -> UserContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(authorization.removeprefix("Bearer ").strip(), JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = get_user(payload["sub"])
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Account is inactive or unavailable")
        return UserContext(username=user.email, role=user.role, is_admin=user.is_admin)
    except HTTPException:
        raise
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

def change_password(payload: ChangePasswordRequest, user: UserContext) -> dict[str, str]:
    current_password = payload.current_password.get_secret_value()
    new_password = payload.new_password.get_secret_value()
    confirm_password = payload.confirm_password.get_secret_value()
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="New password and confirmation do not match")
    if current_password == new_password:
        raise HTTPException(status_code=400, detail="New password must be different from the current password")
    account = get_user(user.username)
    if not account or not account.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive or unavailable")
    if not verify_password(current_password, account.password_hash):
        logger.warning("Password change rejected username=%s reason=current-password-mismatch", user.username)
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    change_user_password(user.username, new_password)
    logger.info("Password changed username=%s", user.username)
    return {"message": "Password updated successfully"}

def require_devops(user: UserContext = Depends(current_user)) -> UserContext:
    if user.role != "devops":
        raise HTTPException(status_code=403, detail="DevOps access required")
    return user

def require_devops_admin(user: UserContext = Depends(current_user)) -> UserContext:
    if user.role != "devops" or not user.is_admin:
        raise HTTPException(status_code=403, detail="DevOps administrator access required")
    return user
