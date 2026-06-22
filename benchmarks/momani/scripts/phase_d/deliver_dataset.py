#!/usr/bin/env python3

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import h5py
import numpy as np

NAVGEN_ROOT = Path(__file__).resolve().parents[2]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from utils.delivery_utils import (  # noqa: E402
    normalize_traj_collision_threshold,
    select_delivery_subset,
)
from utils.hdf5_utils import summarize_generation_metrics, write_generated_dataset  # noqa: E402


DEFAULT_INPUT_HDF5 = str(NAVGEN_ROOT / "datasets/momani/v1/r5/r5_g4_rcvenv_n90.hdf5")
DEFAULT_OUTPUT_HDF5 = str(
    NAVGEN_ROOT / "datasets/momani/v1/r5/r5_g4_rcvenv_n90_delivery.hdf5"
)
DEFAULT_SUMMARY_OUTPUT = str(
    NAVGEN_ROOT / "metrics/phase_d/r5/r5_g4_rcvenv_n90_delivery_summary.json"
)


def _decode_attr(v: Any, default: str = "") -> str:
    if v is None:
        return default
    if isinstance(v, bytes):
        return v.decode("utf-8")
    return str(v)


def _demo_sort_key(name: str) -> Tuple[int, Any]:
    if name.startswith("demo_"):
        suf = name.split("demo_", 1)[1]
        if suf.isdigit():
            return (0, int(suf))
    return (1, name)


def _safe_float(v: Any, default: float) -> float:
    try:
        out = float(v)
        if not math.isfinite(out):
            return float(default)
        return out
    except Exception:
        return float(default)


def _read_records(input_hdf5: str) -> Tuple[List[Dict[str, Any]], str]:
    records: List[Dict[str, Any]] = []
    with h5py.File(input_hdf5, "r") as f:
        data_grp = f["data"]
        env_args_raw = _decode_attr(data_grp.attrs.get("env_args", "{}"), default="{}")
        for demo_id in sorted(list(data_grp.keys()), key=_demo_sort_key):
            grp = data_grp[demo_id]
            traj_len = int(grp["states"].shape[0])
            collision_steps = int(grp.attrs.get("collision_steps", 0))
            has_collision = bool(grp.attrs.get("has_collision", collision_steps > 0))
            collision_step_rate = _safe_float(
                grp.attrs.get(
                    "collision_step_rate", collision_steps / max(traj_len, 1)
                ),
                default=float(collision_steps / max(traj_len, 1)),
            )
            records.append(
                {
                    "demo_id": demo_id,
                    "source_demo_id": _decode_attr(
                        grp.attrs.get("source_demo_id", demo_id), default=demo_id
                    ),
                    "success": bool(grp.attrs.get("success", False)),
                    "has_collision": bool(has_collision),
                    "collision_steps": int(collision_steps),
                    "collision_step_rate": float(collision_step_rate),
                    "final_pos_error": _safe_float(
                        grp.attrs.get("final_pos_error", math.inf), default=math.inf
                    ),
                    "final_yaw_error_deg": _safe_float(
                        grp.attrs.get("final_yaw_error_deg", math.inf), default=math.inf
                    ),
                    "generated_traj_len": int(traj_len),
                }
            )
    return records, env_args_raw


def _load_selected_demos(
    input_hdf5: str, selected_records: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    selected_demo_ids = [str(r["demo_id"]) for r in selected_records]
    out: List[Dict[str, Any]] = []
    with h5py.File(input_hdf5, "r") as f:
        data_grp = f["data"]
        for demo_id in selected_demo_ids:
            grp = data_grp[demo_id]
            states = np.asarray(grp["states"][:], dtype=np.float64)
            actions = np.asarray(grp["actions"][:], dtype=np.float32)
            traj_len = int(states.shape[0])
            if "rewards" in grp:
                rewards = np.asarray(grp["rewards"][:], dtype=np.float32)
            else:
                rewards = np.zeros((traj_len,), dtype=np.float32)
            if "dones" in grp:
                dones = np.asarray(grp["dones"][:], dtype=np.bool_)
            else:
                dones = np.zeros((traj_len,), dtype=np.bool_)

            ep_meta_raw = _decode_attr(grp.attrs.get("ep_meta", "{}"), default="{}")
            generation_meta_raw = _decode_attr(
                grp.attrs.get("generation_meta", "{}"), default="{}"
            )
            try:
                ep_meta = json.loads(ep_meta_raw)
            except Exception:
                ep_meta = {}
            try:
                generation_meta = json.loads(generation_meta_raw)
            except Exception:
                generation_meta = {}

            collision_steps = int(grp.attrs.get("collision_steps", 0))
            collision_step_rate = _safe_float(
                grp.attrs.get(
                    "collision_step_rate", collision_steps / max(traj_len, 1)
                ),
                default=float(collision_steps / max(traj_len, 1)),
            )
            out.append(
                {
                    "generated_demo_id": demo_id,
                    "source_demo_id": _decode_attr(
                        grp.attrs.get("source_demo_id", demo_id), default=demo_id
                    ),
                    "layout_id": int(grp.attrs.get("layout_id", -1)),
                    "style_id": int(grp.attrs.get("style_id", -1)),
                    "ep_meta": ep_meta,
                    "states": states,
                    "actions": actions,
                    "rewards": rewards,
                    "dones": dones,
                    "success": bool(grp.attrs.get("success", False)),
                    "stop_reason": _decode_attr(
                        grp.attrs.get("stop_reason", "unknown"), default="unknown"
                    ),
                    "final_pos_error": _safe_float(
                        grp.attrs.get("final_pos_error", math.inf), default=math.inf
                    ),
                    "final_yaw_error_deg": _safe_float(
                        grp.attrs.get("final_yaw_error_deg", math.inf), default=math.inf
                    ),
                    "generated_traj_len": int(traj_len),
                    "collision_steps": int(collision_steps),
                    "collision_step_rate": float(collision_step_rate),
                    "has_collision": bool(
                        grp.attrs.get("has_collision", collision_steps > 0)
                    ),
                    "generation_meta": generation_meta,
                }
            )
    return out


def _build_shortage_summary(
    records: List[Dict[str, Any]],
    target_count: int,
    threshold: float,
    success_only: bool,
    error_message: str,
) -> Dict[str, Any]:
    total_count = len(records)
    eligible = [
        r for r in records if (bool(r.get("success", False)) or (not success_only))
    ]
    non_collision = [r for r in eligible if not bool(r.get("has_collision", False))]
    allowed_collision = int(math.floor(threshold * target_count + 1e-9))
    min_non_collision_needed = int(target_count - allowed_collision)

    observed_non_collision_rate = float(len(non_collision) / max(total_count, 1))
    recommended_raw_count = None
    if observed_non_collision_rate > 0.0:
        recommended_raw_count = int(
            math.ceil(min_non_collision_needed / observed_non_collision_rate)
        )

    return {
        "status": "insufficient",
        "error": error_message,
        "target_count": int(target_count),
        "traj_collision_threshold": float(threshold),
        "success_only": bool(success_only),
        "strict_shortage_policy": "fail",
        "raw_total_count": int(total_count),
        "eligible_count": int(len(eligible)),
        "eligible_non_collision_count": int(len(non_collision)),
        "allowed_collision_count": int(allowed_collision),
        "min_non_collision_needed": int(min_non_collision_needed),
        "recommended_raw_count": recommended_raw_count,
    }


def deliver_dataset(
    input_hdf5: str,
    output_hdf5: str,
    target_count: int,
    traj_collision_threshold: float,
    success_only: bool = True,
    summary_output: str = DEFAULT_SUMMARY_OUTPUT,
    dry_run: bool = False,
) -> Dict[str, Any]:
    threshold = normalize_traj_collision_threshold(traj_collision_threshold)
    records, env_args_raw = _read_records(input_hdf5=input_hdf5)

    try:
        selection = select_delivery_subset(
            records=records,
            target_count=int(target_count),
            traj_collision_threshold=threshold,
            success_only=bool(success_only),
        )
    except ValueError as exc:
        summary = _build_shortage_summary(
            records=records,
            target_count=int(target_count),
            threshold=threshold,
            success_only=bool(success_only),
            error_message=str(exc),
        )
        if summary_output:
            out = Path(summary_output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8"
            )
        raise

    selected_records = selection["selected_records"]
    selected_demos = _load_selected_demos(
        input_hdf5=input_hdf5,
        selected_records=selected_records,
    )

    if not dry_run:
        write_generated_dataset(
            output_hdf5_path=output_hdf5,
            demos=selected_demos,
            env_args_raw=env_args_raw,
        )

    metric_summary = summarize_generation_metrics(selected_demos)
    summary: Dict[str, Any] = {
        "status": "ok",
        "input_hdf5": str(input_hdf5),
        "output_hdf5": str(output_hdf5),
        "target_count": int(target_count),
        "selected_count": int(len(selected_demos)),
        "traj_collision_threshold": float(threshold),
        "success_only": bool(success_only),
        "strict_shortage_policy": "fail",
        "dry_run": bool(dry_run),
        "eligible_count": int(selection["eligible_count"]),
        "available_non_collision_count": int(
            selection["available_non_collision_count"]
        ),
        "available_collision_count": int(selection["available_collision_count"]),
        "allowed_collision_count": int(selection["allowed_collision_count"]),
        "selected_collision_count": int(selection["selected_collision_count"]),
        "selected_traj_collision_rate": float(
            selection["selected_traj_collision_rate"]
        ),
        "metrics": metric_summary,
    }

    out = Path(summary_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Deliver clean dataset by collision threshold"
    )
    parser.add_argument("--input-hdf5", default=DEFAULT_INPUT_HDF5)
    parser.add_argument("--output-hdf5", default=DEFAULT_OUTPUT_HDF5)
    parser.add_argument("--target-count", type=int, required=True)
    parser.add_argument("--traj-collision-threshold", type=float, required=True)
    parser.add_argument(
        "--success-only", dest="success_only", action="store_true", default=True
    )
    parser.add_argument("--include-failed", dest="success_only", action="store_false")
    parser.add_argument("--summary-output", default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    summary = deliver_dataset(
        input_hdf5=args.input_hdf5,
        output_hdf5=args.output_hdf5,
        target_count=args.target_count,
        traj_collision_threshold=args.traj_collision_threshold,
        success_only=args.success_only,
        summary_output=args.summary_output,
        dry_run=args.dry_run,
    )
    print(f"[deliver_dataset] status={summary['status']}")
    print(f"[deliver_dataset] summary: {args.summary_output}")
    if not args.dry_run:
        print(f"[deliver_dataset] output_hdf5: {args.output_hdf5}")
    print(
        "[deliver_dataset] "
        f"selected={summary['selected_count']}/{summary['target_count']} "
        f"traj_collision_rate={summary['selected_traj_collision_rate']:.4f}"
    )


if __name__ == "__main__":
    main()
