from __future__ import annotations

from typing import Any

from .common import clone_release_pipeline


def _customize(definition: dict[str, Any], _: str, __: str) -> dict[str, Any]:
    """Collections keeps all cloned stages, tasks and variables unchanged."""
    return definition


def create_collections_release_pipeline(
    reference_repository_name: str,
    target_repository_name: str,
    target_build_pipeline: dict[str, Any],
    pat: str,
) -> dict[str, Any]:
    return clone_release_pipeline(
        reference_repository_name,
        target_repository_name,
        target_build_pipeline,
        pat,
        _customize,
    )
