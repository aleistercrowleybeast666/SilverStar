"""Check ordinary Windows collection paths without changing their contents."""
from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import PureWindowsPath


def DestinationPaths_Validate(
    directory: str | os.PathLike[str],
    destinations: Iterable[str],
    *,
    windows: bool | None = None,
) -> None:
    """Reserve the terminating NUL within Windows' ordinary MAX_PATH of 260."""
    if not (os.name == "nt" if windows is None else windows):
        return
    for destination in destinations:
        path = str(PureWindowsPath(directory) / destination)
        units = len(path.encode("utf-16-le", errors="surrogatepass")) // 2
        if units >= 260:
            raise RuntimeError(
                f"Windows portable destination needs {units} UTF-16 code units "
                f"(maximum 259 before the terminating NUL): {path}. "
                "Use a shorter --distpath (build_candidate.ps1 -Destination), "
                "for example D:/python_software/SilverStar/dist/gcf1111; "
                "also extract the delivered ZIP below a short directory."
            )
