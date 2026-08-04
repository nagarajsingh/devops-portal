from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Role = Literal["developer", "devops"]


class UserContext(BaseModel):
    username: str
    role: Role
