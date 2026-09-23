from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, SecretStr, field_validator

from .auth import require_devops
from .logging_config import get_logger
from .models import UserContext
from .repo_sync import execute_uat_repository_sync, preview_uat_repository_sync

router = APIRouter(prefix="/repo-sync", tags=["Repository Sync"])
logger = get_logger("repo-sync-routes")


class RepoSyncRequest(BaseModel):
    target_repositories: list[str] = Field(min_length=1, max_length=30)
    reference_repository: str = Field(default="", max_length=200)
    azure_devops_pat: SecretStr = Field(min_length=10)

    @field_validator("target_repositories")
    @classmethod
    def normalize_targets(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            name = item.strip()
            if not name:
                continue
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                cleaned.append(name)
        if not cleaned:
            raise ValueError("Provide at least one target repository")
        return cleaned


def _run_batch(payload: RepoSyncRequest, user: UserContext, execute: bool) -> dict[str, Any]:
    pat = payload.azure_devops_pat.get_secret_value()
    results: list[dict[str, Any]] = []
    for repository in payload.target_repositories:
        try:
            if execute:
                result = execute_uat_repository_sync(
                    repository,
                    payload.reference_repository,
                    pat,
                    user.username,
                )
            else:
                result = preview_uat_repository_sync(
                    repository,
                    payload.reference_repository,
                    pat,
                )
            results.append(result)
        except Exception as exc:
            logger.exception(
                "Repository sync %s failed actor=%s repository=%s",
                "execution" if execute else "preview",
                user.username,
                repository,
            )
            results.append(
                {
                    "repository": repository,
                    "reference_repository": payload.reference_repository.strip() or repository,
                    "source_branch": "develop",
                    "target_branch": "release/uat",
                    "status": "Failed" if execute else "Preview Failed",
                    "error": str(exc) or "Repository sync failed",
                    "files": [],
                    "warnings": [],
                }
            )
    return {
        "mode": "execute" if execute else "preview",
        "results": results,
    }


@router.post("/preview")
def preview_repo_sync(
    payload: RepoSyncRequest,
    user: UserContext = Depends(require_devops),
) -> dict[str, Any]:
    logger.info(
        "Repository sync preview actor=%s targets=%s reference=%s",
        user.username,
        payload.target_repositories,
        payload.reference_repository or "self",
    )
    return _run_batch(payload, user, execute=False)


@router.post("/execute")
def execute_repo_sync(
    payload: RepoSyncRequest,
    user: UserContext = Depends(require_devops),
) -> dict[str, Any]:
    logger.info(
        "Repository sync execution actor=%s targets=%s reference=%s",
        user.username,
        payload.target_repositories,
        payload.reference_repository or "self",
    )
    return _run_batch(payload, user, execute=True)
