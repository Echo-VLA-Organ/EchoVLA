#!/usr/bin/env python3
"""Echo_VLA entry point for the MoMani NavigateKitchen benchmark."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys

import _repo_bootstrap

_repo_bootstrap.ensure_repo_on_path()
from utils.bootstrap import bootstrap_echo_vla
from utils.momani_bridge import (
    apply_momani_echo_env,
    default_echo_base_config,
    default_momani_dataset,
    get_momani_root,
)

log = logging.getLogger(__name__)

SUBCOMMANDS = ("closed_loop", "deliver", "runtime_check")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run MoMani NavigateKitchen benchmark from Echo_VLA",
    )
    parser.add_argument(
        "command",
        choices=SUBCOMMANDS,
        help="closed_loop: phase-B eval; deliver: phase-D dataset delivery; runtime_check: env manifest",
    )
    parser.add_argument("--dataset", default=None, help="HDF5 file or RoboCasa365 LeRobot root")
    parser.add_argument("--n", type=int, default=10, help="closed_loop: number of demos/plans")
    parser.add_argument("--nav-stitch", action="store_true", help="closed_loop: multi-leg nav stitching")
    parser.add_argument("--stitch-length", type=int, default=3, help="legs per stitched nav plan")
    parser.add_argument("--output", default=None, help="metrics JSON output path")
    parser.add_argument("--input-hdf5", default=None, help="deliver: source HDF5")
    parser.add_argument("--output-hdf5", default=None, help="deliver: filtered HDF5")
    parser.add_argument("--target-count", type=int, default=None, help="deliver: sample count")
    parser.add_argument(
        "--traj-collision-threshold",
        type=float,
        default=None,
        help="deliver: 0 / 0.1 / 0.2",
    )
    parser.add_argument("--dry-run", action="store_true", help="deliver: evaluate only")
    parser.add_argument("extra", nargs=argparse.REMAINDER, help="Extra args forwarded to MoMani script")
    return parser


def _python() -> str:
    venv_py = get_momani_root() / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def _run_script(script_rel: str, argv: list[str]) -> int:
    momani = get_momani_root()
    script = momani / script_rel
    if not script.is_file():
        log.error("MoMani script not found: %s", script)
        return 1
    cmd = [_python(), str(script), *argv]
    log.info("Running: %s", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(momani))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    bootstrap_echo_vla()
    apply_momani_echo_env()

    args = _build_parser().parse_args()
    momani = get_momani_root()
    dataset = args.dataset or str(default_momani_dataset())
    base_cfg = str(default_echo_base_config())

    if args.command == "closed_loop":
        suffix = "stitch" if args.nav_stitch else "closed_loop"
        output = args.output or str(
            momani / "metrics" / "phase_b" / f"echo_{suffix}_eval_{args.n}.json"
        )
        argv = [
            "--base-config", base_cfg,
            "--dataset", dataset,
            "--n", str(args.n),
            "--output", output,
        ]
        if args.nav_stitch:
            argv.extend(["--nav-stitch", "--stitch-length", str(args.stitch_length)])
        argv.extend(args.extra)
        return _run_script("scripts/phase_b/test_closed_loop.py", argv)

    if args.command == "deliver":
        if args.target_count is None or args.traj_collision_threshold is None:
            log.error("deliver requires --target-count and --traj-collision-threshold")
            return 2
        input_hdf5 = args.input_hdf5 or str(momani / "datasets" / "momani" / "v1" / "latest.hdf5")
        output_hdf5 = args.output_hdf5 or str(
            momani / "datasets" / "momani" / "v1" / f"delivery_t{int(args.traj_collision_threshold * 10):02d}_n{args.target_count}.hdf5"
        )
        summary = args.output or str(
            momani / "metrics" / "phase_d" / f"delivery_t{int(args.traj_collision_threshold * 10):02d}_n{args.target_count}_summary.json"
        )
        argv = [
            "--input-hdf5", input_hdf5,
            "--output-hdf5", output_hdf5,
            "--target-count", str(args.target_count),
            "--traj-collision-threshold", str(args.traj_collision_threshold),
            "--summary-output", summary,
        ]
        if args.dry_run:
            argv.append("--dry-run")
        argv.extend(args.extra)
        return _run_script("scripts/phase_d/deliver_dataset.py", argv)

    manifest = str(momani / "config" / "runtime" / "runtime_manifest.yaml")
    return _run_script("scripts/env/check_runtime.py", ["--manifest", manifest, *args.extra])


if __name__ == "__main__":
    raise SystemExit(main())
