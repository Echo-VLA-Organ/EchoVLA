import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np


def _require_h5py():
    import h5py

    return h5py


def build_generation_schedule(
    source_demo_ids: Sequence[str],
    target_count: int,
    seed: int = 42,
) -> List[str]:
    ids = list(source_demo_ids)
    if len(ids) == 0:
        raise ValueError("source_demo_ids is empty")
    if target_count <= 0:
        return []

    rng = np.random.default_rng(seed)
    schedule: List[str] = []
    pool = list(ids)
    while len(schedule) < target_count:
        rng.shuffle(pool)
        schedule.extend(pool)
    return schedule[:target_count]


def summarize_generation_metrics(
    per_demo_metrics: List[Dict[str, Any]],
) -> Dict[str, Any]:
    total = len(per_demo_metrics)
    success_count = sum(1 for m in per_demo_metrics if bool(m.get("success", False)))
    collision_steps_total = sum(
        int(m.get("collision_steps", 0)) for m in per_demo_metrics
    )
    steps_total = sum(int(m.get("generated_traj_len", 0)) for m in per_demo_metrics)
    traj_collision_count = sum(
        1
        for m in per_demo_metrics
        if bool(m.get("has_collision", False)) or int(m.get("collision_steps", 0)) > 0
    )

    def _avg(key: str):
        if total == 0:
            return None
        return float(sum(float(m.get(key, 0.0)) for m in per_demo_metrics) / total)

    stop_reason_counter = Counter(
        str(m.get("stop_reason", "unknown")) for m in per_demo_metrics
    )
    layout_buckets: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"count": 0, "success": 0}
    )
    for m in per_demo_metrics:
        lid = str(m.get("layout_id", "None"))
        layout_buckets[lid]["count"] += 1
        if bool(m.get("success", False)):
            layout_buckets[lid]["success"] += 1

    failures = [
        {
            "generated_demo_id": m.get("generated_demo_id"),
            "source_demo_id": m.get("source_demo_id"),
            "layout_id": m.get("layout_id"),
            "style_id": m.get("style_id"),
            "final_pos_error": m.get("final_pos_error"),
            "final_yaw_error_deg": m.get("final_yaw_error_deg"),
            "stop_reason": m.get("stop_reason"),
            "collision_steps": int(m.get("collision_steps", 0)),
            "collision_step_rate": float(m.get("collision_step_rate", 0.0)),
        }
        for m in per_demo_metrics
        if not bool(m.get("success", False))
    ]

    return {
        "total_demos": total,
        "success_count": success_count,
        "success_rate": float(success_count / total) if total else None,
        "avg_traj_len": _avg("generated_traj_len"),
        "avg_pos_error": _avg("final_pos_error"),
        "avg_yaw_error_deg": _avg("final_yaw_error_deg"),
        "avg_timeout_waypoints": _avg("timeout_waypoints"),
        "collision_steps_total": int(collision_steps_total),
        "steps_total": int(steps_total),
        "collision_step_rate": float(collision_steps_total / max(steps_total, 1)),
        "traj_collision_count": int(traj_collision_count),
        "traj_collision_rate": float(traj_collision_count / max(total, 1)),
        "avg_collision_steps": _avg("collision_steps"),
        "layout_breakdown": dict(layout_buckets),
        "stop_reason_breakdown": dict(stop_reason_counter),
        "failure_cases": failures,
    }


def write_generated_dataset(
    output_hdf5_path: str,
    demos: List[Dict[str, Any]],
    env_args_raw: str,
):
    out_path = Path(output_hdf5_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    h5py = _require_h5py()
    with h5py.File(str(out_path), "w") as f:
        data_grp = f.create_group("data")
        data_grp.attrs["env_args"] = env_args_raw
        data_grp.attrs["total"] = len(demos)

        mask_grp = f.create_group("mask")
        all_demo_names = [f"demo_{i}" for i in range(len(demos))]
        mask_grp.create_dataset(
            "all",
            data=np.array(
                [name.encode("utf-8") for name in all_demo_names], dtype="S20"
            ),
        )

        for i, demo in enumerate(demos):
            name = f"demo_{i}"
            grp = data_grp.create_group(name)

            states = np.asarray(demo["states"], dtype=np.float64)
            actions = np.asarray(demo["actions"], dtype=np.float32)
            rewards = np.asarray(demo["rewards"], dtype=np.float32)
            dones = np.asarray(demo["dones"], dtype=np.bool_)

            grp.create_dataset("states", data=states, compression="gzip")
            grp.create_dataset("actions", data=actions, compression="gzip")
            grp.create_dataset("rewards", data=rewards, compression="gzip")
            grp.create_dataset("dones", data=dones, compression="gzip")

            grp.attrs["source_demo_id"] = str(demo.get("source_demo_id"))
            grp.attrs["layout_id"] = int(demo.get("layout_id", -1))
            grp.attrs["style_id"] = int(demo.get("style_id", -1))
            grp.attrs["success"] = bool(demo.get("success", False))
            grp.attrs["final_pos_error"] = float(demo.get("final_pos_error", 0.0))
            grp.attrs["final_yaw_error_deg"] = float(
                demo.get("final_yaw_error_deg", 0.0)
            )
            grp.attrs["stop_reason"] = str(demo.get("stop_reason", "unknown"))
            grp.attrs["collision_steps"] = int(demo.get("collision_steps", 0))
            grp.attrs["collision_step_rate"] = float(
                demo.get("collision_step_rate", 0.0)
            )
            grp.attrs["has_collision"] = bool(demo.get("has_collision", False))
            grp.attrs["ep_meta"] = json.dumps(
                demo.get("ep_meta", {}), ensure_ascii=True
            )
            grp.attrs["generation_meta"] = json.dumps(
                demo.get("generation_meta", {}),
                ensure_ascii=True,
            )
