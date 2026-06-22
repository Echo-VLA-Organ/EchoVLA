#!/usr/bin/env python3

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import h5py
import numpy as np

import sys

NAVGEN_ROOT = Path(__file__).resolve().parents[2]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from data_gen import SceneManager
from utils.collision_metrics import count_mobile_contacts_from_sim


DEFAULT_OFFICIAL = str(NAVGEN_ROOT / "datasets/official/NavigateKitchen/demo.hdf5")
DEFAULT_GENERATED = str(NAVGEN_ROOT / "datasets/momani/v1/demo.hdf5")
DEFAULT_OUT_JSON = str(NAVGEN_ROOT / "metrics/phase_d/collision_audit.json")
DEFAULT_OUT_MD = str(NAVGEN_ROOT / "reports/phase_d/collision_audit.md")


def _demo_sort_key(name: str):
    if name.startswith("demo_"):
        suf = name.split("demo_", 1)[1]
        if suf.isdigit():
            return (0, int(suf))
    return (1, name)


def _decode(v):
    if isinstance(v, bytes):
        return v.decode("utf-8")
    return v


def audit_dataset(
    dataset_path: str,
    source_scene_dataset_path: str,
    mobile_prefix: str = "mobilebase0",
) -> Dict[str, Any]:
    sm = SceneManager(source_scene_dataset_path)
    env = sm.build_env(force_offscreen=False)

    traj_total = 0
    traj_with_collision = 0
    steps_total = 0
    collision_steps_total = 0
    geom_counter = Counter()
    per_demo = []

    with h5py.File(dataset_path, "r") as f:
        demo_names = sorted(list(f["data"].keys()), key=_demo_sort_key)
        for demo_name in demo_names:
            grp = f["data"][demo_name]
            states = grp["states"][:]

            source_demo_id = _decode(grp.attrs.get("source_demo_id", demo_name))
            source_states, _ = sm.read_demo_arrays(source_demo_id)
            sm.reset_env_to_demo_scene(
                env, source_demo_id, initial_state=source_states[0]
            )

            traj_total += 1
            demo_collision_steps = 0
            for s in states:
                env.sim.set_state_from_flattened(np.asarray(s, dtype=np.float64))
                env.sim.forward()
                steps_total += 1
                out = count_mobile_contacts_from_sim(
                    env.sim, mobile_prefix=mobile_prefix
                )
                c = int(out["total_contacts"])
                if c > 0:
                    demo_collision_steps += 1
                    for geom_name, cnt in out["target_counter"].items():
                        geom_counter[geom_name] += int(cnt)

            if demo_collision_steps > 0:
                traj_with_collision += 1
            collision_steps_total += demo_collision_steps

            success_attr = grp.attrs.get("success", None)
            success: Optional[bool]
            if success_attr is None:
                success = None
            else:
                success = bool(success_attr)

            per_demo.append(
                {
                    "demo_id": demo_name,
                    "source_demo_id": source_demo_id,
                    "traj_len": int(states.shape[0]),
                    "collision_steps": int(demo_collision_steps),
                    "collision_step_rate": float(
                        demo_collision_steps / max(int(states.shape[0]), 1)
                    ),
                    "has_collision": bool(demo_collision_steps > 0),
                    "success": success,
                }
            )

    summary = {
        "traj_total": int(traj_total),
        "traj_with_collision": int(traj_with_collision),
        "traj_collision_rate": float(traj_with_collision / max(traj_total, 1)),
        "steps_total": int(steps_total),
        "collision_steps_total": int(collision_steps_total),
        "step_collision_rate": float(collision_steps_total / max(steps_total, 1)),
        "top_collision_geoms": geom_counter.most_common(30),
    }

    success_rows = [r for r in per_demo if r["success"] is True]
    fail_rows = [r for r in per_demo if r["success"] is False]
    if success_rows:
        s_steps = sum(r["traj_len"] for r in success_rows)
        s_cols = sum(r["collision_steps"] for r in success_rows)
        summary["success_subset"] = {
            "n_traj": len(success_rows),
            "step_collision_rate": float(s_cols / max(s_steps, 1)),
        }
    if fail_rows:
        f_steps = sum(r["traj_len"] for r in fail_rows)
        f_cols = sum(r["collision_steps"] for r in fail_rows)
        summary["failure_subset"] = {
            "n_traj": len(fail_rows),
            "step_collision_rate": float(f_cols / max(f_steps, 1)),
        }

    return {
        "dataset_path": dataset_path,
        "source_scene_dataset_path": source_scene_dataset_path,
        "mobile_prefix": mobile_prefix,
        "summary": summary,
        "per_demo": per_demo,
    }


def _render_md(report: Dict[str, Any]) -> str:
    s = report["summary"]
    lines = []
    lines.append("# Collision Audit")
    lines.append("")
    lines.append(f"- dataset: `{report['dataset_path']}`")
    lines.append(f"- source scenes: `{report['source_scene_dataset_path']}`")
    lines.append(f"- traj collision rate: {s['traj_collision_rate']:.4f}")
    lines.append(f"- step collision rate: {s['step_collision_rate']:.4f}")
    lines.append("")
    if "success_subset" in s:
        lines.append("## Success Subset")
        lines.append(
            f"- n={s['success_subset']['n_traj']}, step_collision_rate={s['success_subset']['step_collision_rate']:.4f}"
        )
        lines.append("")
    if "failure_subset" in s:
        lines.append("## Failure Subset")
        lines.append(
            f"- n={s['failure_subset']['n_traj']}, step_collision_rate={s['failure_subset']['step_collision_rate']:.4f}"
        )
        lines.append("")
    lines.append("## Top Collision Geoms")
    for g, c in s["top_collision_geoms"][:20]:
        lines.append(f"- {g}: {c}")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Collision audit for generated/official datasets"
    )
    parser.add_argument("--dataset", default=DEFAULT_GENERATED)
    parser.add_argument("--source-scenes", default=DEFAULT_OFFICIAL)
    parser.add_argument("--mobile-prefix", default="mobilebase0")
    parser.add_argument("--json-output", default=DEFAULT_OUT_JSON)
    parser.add_argument("--md-output", default=DEFAULT_OUT_MD)
    args = parser.parse_args()

    report = audit_dataset(
        dataset_path=args.dataset,
        source_scene_dataset_path=args.source_scenes,
        mobile_prefix=args.mobile_prefix,
    )

    out_json = Path(args.json_output)
    out_md = Path(args.md_output)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    out_md.write_text(_render_md(report), encoding="utf-8")

    s = report["summary"]
    print(f"[collision_audit] json: {out_json}")
    print(f"[collision_audit] md: {out_md}")
    print(
        f"[collision_audit] traj_collision_rate={s['traj_collision_rate']:.4f}, "
        f"step_collision_rate={s['step_collision_rate']:.4f}"
    )


if __name__ == "__main__":
    main()
