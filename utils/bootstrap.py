"""Minimal bootstrap for EchoVLA benchmark package."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT: Path | None = None


def get_repo_root() -> Path:
    global _REPO_ROOT
    if _REPO_ROOT is not None:
        return _REPO_ROOT
    env_root = os.environ.get("ECHO_VLA_ROOT")
    if env_root:
        _REPO_ROOT = Path(env_root).expanduser().resolve()
    else:
        _REPO_ROOT = Path(__file__).resolve().parents[1]
    return _REPO_ROOT


def bootstrap_echo_vla(*, setup_tmp: bool = False) -> Path:
    root = get_repo_root()
    root_s = str(root)
    os.environ.setdefault("ECHO_VLA_ROOT", root_s)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    if setup_tmp:
        tmp = os.environ.get("ECHO_TMPDIR", str(root / ".tmp"))
        os.makedirs(tmp, exist_ok=True)
    return root
