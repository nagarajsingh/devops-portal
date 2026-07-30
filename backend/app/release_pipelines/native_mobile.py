from __future__ import annotations

from typing import Any

from .common import clone_release_pipeline


def _update_helm_inputs(value: Any, target_repository_name: str) -> None:
    if isinstance(value, list):
        for item in value:
            _update_helm_inputs(item, target_repository_name)
        return
    if not isinstance(value, dict):
        return

    inputs = value.get("inputs")
    if isinstance(inputs, dict):
        for key in list(inputs):
            normalized = key.lower().replace("_", "").replace("-", "")
            if normalized in {"chartpath", "chartspath"}:
                inputs[key] = (
                    f"$(System.DefaultWorkingDirectory)/_{target_repository_name}/helm-charts"
                )
            elif normalized in {"chartversion", "version"}:
                inputs[key] = "1.0.0"
            elif normalized in {"releasename", "helmreleasename"}:
                inputs[key] = target_repository_name
            elif normalized in {"overridevalues", "setvalues", "arguments"}:
                current = str(inputs.get(key) or "")
                if "environment=$(environment)" in current or normalized in {"overridevalues", "setvalues"}:
                    inputs[key] = "environment=$(environment)"
            elif normalized in {"valuefile", "valuefiles", "valuesfile", "valuesfiles"}:
                inputs[key] = (
                    f"$(System.DefaultWorkingDirectory)/_{target_repository_name}/"
                    "helm-charts/values-$(environment).yaml"
                )

    for item in value.values():
        _update_helm_inputs(item, target_repository_name)


def _customize(
    definition: dict[str, Any],
    _: str,
    target_repository_name: str,
) -> dict[str, Any]:
    """Update only Native-Mobile Helm-specific task inputs after cloning."""
    _update_helm_inputs(definition, target_repository_name)
    return definition


def create_native_mobile_release_pipeline(
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
