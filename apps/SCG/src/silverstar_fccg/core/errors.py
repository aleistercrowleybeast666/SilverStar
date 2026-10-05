from __future__ import annotations

import re
from typing import Any


class FccgError(ValueError):
    """Stable user-facing error code plus non-translated technical diagnostics."""

    def __init__(
        self,
        code: str,
        params: dict[str, Any] | None = None,
        technical_detail: str = "",
    ) -> None:
        if not code.startswith("error."):
            technical_detail = technical_detail or code
            class_name = type(self).__name__.removesuffix("Error")
            code = "error." + re.sub(
                r"(?<!^)(?=[A-Z])", "_", class_name
            ).casefold()
        self.code = code
        self.params = dict(params or {})
        self.technical_detail = technical_detail or code
        super().__init__(self.technical_detail)

    def __str__(self) -> str:
        return self.technical_detail
