"""One-line repo bootstrap for entry scripts (import before utils.*)."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_on_path() -> Path:
    root = Path(__file__).resolve().parent
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return root


def install_repo_path_from(caller_file: str | Path) -> Path:
    """Walk parents of caller_file until Echo_VLA root (_repo_bootstrap.py) is found."""
    start = Path(caller_file).resolve().parent
    for anc in [start, *start.parents]:
        if (anc / "_repo_bootstrap.py").is_file():
            root_s = str(anc)
            if root_s not in sys.path:
                sys.path.insert(0, root_s)
            return anc
    raise RuntimeError(f"Echo_VLA root not found above {caller_file}")
