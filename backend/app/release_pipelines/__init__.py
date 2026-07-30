from __future__ import annotations

from typing import Any, Callable

from .collections import create_collections_release_pipeline
from .h2h import create_h2h_release_pipeline
from .native_mobile import create_native_mobile_release_pipeline
from .safenet import create_safenet_release_pipeline

ReleaseCreator = Callable[[str, str, dict[str, Any], str], dict[str, Any]]

_CREATORS: dict[str, ReleaseCreator] = {
    "H2H": create_h2h_release_pipeline,
    "Collections": create_collections_release_pipeline,
    "Native-Mobile": create_native_mobile_release_pipeline,
    "Safenet": create_safenet_release_pipeline,
}


def create_release_pipeline(
    application_type: str,
    reference_repository_name: str,
    target_repository_name: str,
    target_build_pipeline: dict[str, Any],
    pat: str,
) -> dict[str, Any]:
    creator = _CREATORS.get(application_type)
    if not creator:
        raise RuntimeError(f"Release pipeline cloning is not configured for {application_type}")
    return creator(
        reference_repository_name,
        target_repository_name,
        target_build_pipeline,
        pat,
    )
