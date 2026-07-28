"""Backend package initialization.

Azure DevOps repository item endpoints return JSON for metadata requests and raw
text for file-content requests. The existing shared request helper calls
``json.loads`` for successful responses, so this compatibility wrapper converts
only non-JSON responses originating from that helper into a content payload.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

_original_json_loads = json.loads


def _loads_with_azure_file_support(value: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return _original_json_loads(value, *args, **kwargs)
    except json.JSONDecodeError:
        caller = inspect.currentframe().f_back
        if caller is not None and caller.f_code.co_name == "azdo_request":
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            return {"content": value}
        raise


json.loads = _loads_with_azure_file_support
