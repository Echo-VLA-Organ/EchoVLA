#!/usr/bin/env python3

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Dict, List

import h5py
import numpy as np


NAVGEN_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT = str(NAVGEN_ROOT / "datasets/momani/v1/demo.hdf5")
DEFAULT_JSON_OUT = str(NAVGEN_ROOT / "metrics/phase_d/training_validation.json")
DEFAULT_MD_OUT = str(NAVGEN_ROOT / "reports/phase_d/training_validation.md")


def _safe_stats(vals: List[float]) -> Dict[str, float]:
    if len(vals) == 0:
        return {"min": math.nan, "max": math.nan, "mean": math.nan, "median": math.nan}
    arr = sorted(vals)
    n = len(arr)
    mid = arr[n // 2]
    return {
        "min": float(arr[0]),
        "max": float(arr[-1]),
        "mean": float(sum(arr) / n),
        "median": float(mid),
    }


def validate_dataset(hdf5_path: str) -> Dict:
    path = Path(hdf5_path)
    if not path.exists():
        raise FileNotFoundError(f"missing dataset: {hdf5_path}")

    traj_lens = []
    state_dims = Counter()
    action_dims = Counter()
    layout_counter = Counter()
    stop_reason_counter = Counter()

    success_count = 0
    empty_traj_count = 0
    nan_count = 0
    inf_count = 0
    action_oob_count = 0
    action_min = math.inf
    action_max = -math.inf

    with h5py.File(hdf5_path, "r") as f:
        if "data" not in f:
            raise ValueError("missing top-level group 'data'")

        demos = sorted(list(f["data"].keys()))
        for dname in demos:
            grp = f["data"][dname]
            states = grp["states"][:]
            actions = grp["actions"][:]
            dones = grp["dones"][:]

            traj_lens.append(int(states.shape[0]))
            state_dims[int(states.shape[1]) if states.ndim == 2 else -1] += 1
            action_dims[int(actions.shape[1]) if actions.ndim == 2 else -1] += 1

            if states.shape[0] == 0:
                empty_traj_count += 1

            if bool(grp.attrs.get("success", False)):
                success_count += 1

            layout_counter[str(grp.attrs.get("layout_id", "None"))] += 1
            stop_reason_counter[str(grp.attrs.get("stop_reason", "unknown"))] += 1

            nan_count += int(np.isnan(states).sum() + np.isnan(actions).sum())
            inf_count += int(np.isinf(states).sum() + np.isinf(actions).sum())
            action_oob_count += int((np.abs(actions) > 1.000001).sum())

            if actions.size > 0:
                action_min = min(action_min, float(actions.min()))
                action_max = max(action_max, float(actions.max()))

            if (
                states.shape[0] != actions.shape[0]
                or actions.shape[0] != dones.shape[0]
            ):
                stop_reason_counter["shape_mismatch"] += 1

    total = len(traj_lens)
    return {
        "dataset_path": hdf5_path,
        "total_demos": total,
        "success_count": int(success_count),
        "success_rate": float(success_count / total) if total else None,
        "traj_len_stats": _safe_stats([float(x) for x in traj_lens]),
        "state_dims": dict(state_dims),
        "action_dims": dict(action_dims),
        "empty_traj_count": int(empty_traj_count),
        "nan_count": int(nan_count),
        "inf_count": int(inf_count),
        "action_oob_count": int(action_oob_count),
        "action_range": {
            "min": None if action_min is math.inf else float(action_min),
            "max": None if action_max is -math.inf else float(action_max),
        },
        "layout_coverage": dict(layout_counter),
        "stop_reason_breakdown": dict(stop_reason_counter),
        "pass": bool(
            total > 0
            and empty_traj_count == 0
            and nan_count == 0
            and inf_count == 0
            and action_oob_count == 0
            and "shape_mismatch" not in stop_reason_counter
        ),
    }


def _render_md(report: Dict) -> str:
    lines = []
    lines.append("# Phase D Training Validation")
    lines.append("")
    lines.append(f"- dataset: `{report['dataset_path']}`")
    lines.append(f"- total demos: {report['total_demos']}")
    lines.append(f"- success rate: {report['success_rate']:.4f}")
    lines.append(f"- pass: {report['pass']}")
    lines.append("")
    lines.append("## Trajectory Length")
    tls = report["traj_len_stats"]
    lines.append(
        f"- min={tls['min']:.1f}, max={tls['max']:.1f}, mean={tls['mean']:.1f}, median={tls['median']:.1f}"
    )
    lines.append("")
    lines.append("## Data Integrity")
    lines.append(f"- empty_traj_count: {report['empty_traj_count']}")
    lines.append(f"- nan_count: {report['nan_count']}")
    lines.append(f"- inf_count: {report['inf_count']}")
    lines.append(f"- action_oob_count: {report['action_oob_count']}")
    lines.append(
        f"- action_range: [{report['action_range']['min']}, {report['action_range']['max']}]"
    )
    lines.append("")
    lines.append("## Coverage")
    lines.append(
        f"- layout_coverage: {json.dumps(report['layout_coverage'], ensure_ascii=False)}"
    )
    lines.append(
        f"- stop_reason_breakdown: {json.dumps(report['stop_reason_breakdown'], ensure_ascii=False)}"
    )
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Validate generated dataset for training"
    )
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--json-output", default=DEFAULT_JSON_OUT)
    parser.add_argument("--md-output", default=DEFAULT_MD_OUT)
    args = parser.parse_args()

    report = validate_dataset(args.input)

    json_out = Path(args.json_output)
    md_out = Path(args.md_output)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(
        json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    md_out.write_text(_render_md(report), encoding="utf-8")

    print(f"[training_validation] json: {json_out}")
    print(f"[training_validation] md: {md_out}")
    print(f"[training_validation] pass: {report['pass']}")


if __name__ == "__main__":
    main()
