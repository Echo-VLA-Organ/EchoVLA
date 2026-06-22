"""Bridge EchoVLA to the MoMani NavigateKitchen benchmark."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from utils.bootstrap import get_repo_root


def get_momani_root() -> Path:
    env_root = os.environ.get("ECHO_MOMANI_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return get_repo_root() / "benchmarks" / "momani"


def apply_momani_echo_env() -> Path:
    echo_root = get_repo_root()
    momani_root = get_momani_root()

    os.environ.setdefault("ECHO_MOMANI_ROOT", str(momani_root))
    os.environ.setdefault("NAVGEN_ROOT", str(momani_root))
    os.environ.setdefault("MOMANI_ROOT", str(momani_root))
    os.environ.setdefault("NAVGEN_SKIP_GIT_SYNC", "1")

    robosuite_src = os.environ.get("ROBOSUITE_SRC")
    robocasa_src = os.environ.get("ROBOCASA_SRC")
    if not robosuite_src:
        candidate = echo_root / "custom_robocasa" / "custom_robosuite"
        if candidate.is_dir():
            robosuite_src = str(candidate)
    if not robocasa_src:
        candidate = echo_root / "custom_robocasa" / "custom_robocasa"
        if candidate.is_dir():
            robocasa_src = str(candidate)
    if robosuite_src:
        os.environ.setdefault("ROBOSUITE_SRC", robosuite_src)
    if robocasa_src:
        os.environ.setdefault("ROBOCASA_SRC", robocasa_src)

    momani_s = str(momani_root)
    if momani_s not in sys.path:
        sys.path.insert(0, momani_s)
    if robosuite_src and str(robosuite_src) not in sys.path:
        sys.path.insert(0, str(robosuite_src))

    return momani_root


def default_robocasa365_nav_dataset() -> Path | None:
    override = os.environ.get("ECHO_MOMANI_DATASET") or os.environ.get("ECHO_ROBOCASA365_DATA")
    roots: list[Path] = []
    if override:
        roots.append(Path(override).expanduser())

    patterns = (
        "pretrain/atomic/NavigateKitchen/*/lerobot",
        "pretrain/atomic/NavigateKitchen/*",
        "target/atomic/NavigateKitchen/*/lerobot",
        "target/atomic/NavigateKitchen/*",
    )
    for root in roots:
        root = root.expanduser().resolve()
        for pattern in patterns:
            for match in sorted(root.glob(pattern), reverse=True):
                momani = get_momani_root()
                if str(momani) not in sys.path:
                    sys.path.insert(0, str(momani))
                from utils.dataset_backend import detect_dataset_format

                try:
                    if detect_dataset_format(match) == "lerobot365":
                        return match.resolve()
                except ValueError:
                    continue
    return None


def default_official_dataset_hdf5() -> Path:
    override = os.environ.get("ECHO_MOMANI_OFFICIAL_HDF5")
    if override:
        return Path(override).expanduser().resolve()

    robocasa_data = os.environ.get("ECHO_ROBOCASA_DATA")
    if robocasa_data:
        candidate = (
            Path(robocasa_data).expanduser()
            / "v0.1"
            / "single_stage"
            / "kitchen_navigate"
            / "NavigateKitchen"
            / "2024-05-24"
            / "demo.hdf5"
        )
        if candidate.is_file():
            return candidate.resolve()

    return get_momani_root() / "datasets" / "official" / "NavigateKitchen" / "demo.hdf5"


def default_momani_dataset() -> Path:
    lerobot = default_robocasa365_nav_dataset()
    if lerobot is not None:
        return lerobot
    return default_official_dataset_hdf5()


def default_echo_base_config() -> Path:
    return get_momani_root() / "config" / "echo_base_config.yaml"
