from __future__ import annotations
from fastapi import APIRouter, Depends, Response, status
from .auth import require_devops_admin
from .models import PortalUserCreate, PortalUserResponse, PortalUserUpdate, UserContext
from .user_store import create_user, delete_user, list_users, update_user

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

def view(user) -> PortalUserResponse:
    return PortalUserResponse(id=user.id,email=user.email,role=user.role,is_admin=user.is_admin,is_active=user.is_active,created_at=user.created_at.isoformat(),updated_at=user.updated_at.isoformat())

@router.get("", response_model=list[PortalUserResponse])
def users(_: UserContext = Depends(require_devops_admin)):
    return [view(user) for user in list_users()]

@router.post("", response_model=PortalUserResponse, status_code=201)
def add_user(payload: PortalUserCreate, _: UserContext = Depends(require_devops_admin)):
    return view(create_user(payload.email, payload.password.get_secret_value(), payload.role, payload.is_admin))

@router.put("/{user_id}", response_model=PortalUserResponse)
def edit_user(user_id: int, payload: PortalUserUpdate, admin: UserContext = Depends(require_devops_admin)):
    users_by_id = {user.id: user for user in list_users()}
    target = users_by_id.get(user_id)
    if target and target.email == admin.username and (not payload.is_active or payload.role != "devops" or not payload.is_admin):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="You cannot remove your own active DevOps administrator access")
    return view(update_user(user_id, payload.role, payload.is_admin, payload.is_active, payload.password.get_secret_value() if payload.password else None))

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_user(user_id: int, admin: UserContext = Depends(require_devops_admin)):
    users_by_id = {user.id: user for user in list_users()}
    target = users_by_id.get(user_id)
    if target and target.email == admin.username:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="You cannot delete your own administrator account")
    delete_user(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
