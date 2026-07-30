from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import (
    POWER_AUTOMATE_APPROVAL_ENABLED,
    POWER_AUTOMATE_APPROVAL_URL,
    POWER_AUTOMATE_CALLBACK_TOKEN,
    POWER_AUTOMATE_CALLBACK_URL,
    POWER_AUTOMATE_TIMEOUT_SECONDS,
)
from .logging_config import get_logger

logger = get_logger("power-automate")


def send_power_automate_approval(item: dict) -> bool:
    """Send an app-owner approval request to Power Automate.

    Returns False when the integration is disabled and True when Power Automate
    accepts the request. Sensitive URL and callback-token values are never logged.
    """
    if not POWER_AUTOMATE_APPROVAL_ENABLED:
        logger.debug("Power Automate approval is disabled request_id=%s", item.get("id"))
        return False

    if not POWER_AUTOMATE_APPROVAL_URL:
        raise RuntimeError("POWER_AUTOMATE_APPROVAL_URL must be configured when Power Automate approval is enabled")
    if not POWER_AUTOMATE_CALLBACK_TOKEN:
        raise RuntimeError("POWER_AUTOMATE_CALLBACK_TOKEN must be configured when Power Automate approval is enabled")

    payload = {
        "request_id": item["id"],
        "application": item["application_type"],
        "repository_name": item["repository_name"],
        "app_owner": item["app_owner"],
        "requested_by": item["requested_by"],
        "pipeline_type": item.get("pipeline_type") or "Not selected",
        "reference_repository": item.get("reference_repository_name") or "",
        "ingress_path": item.get("ingress_path") or "",
        "comments": item.get("comments") or "",
        "callback_url": POWER_AUTOMATE_CALLBACK_URL,
        "callback_token": POWER_AUTOMATE_CALLBACK_TOKEN,
    }

    request = urllib.request.Request(
        POWER_AUTOMATE_APPROVAL_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=POWER_AUTOMATE_TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Power Automate returned HTTP {response.status}")
            logger.info(
                "Power Automate approval request accepted request_id=%s app_owner=%s status=%s response_length=%s",
                item["id"],
                item["app_owner"],
                response.status,
                len(response_body),
            )
            return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Power Automate returned HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to connect to Power Automate: {exc.reason}") from exc
