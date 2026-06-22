#!/usr/bin/env python3

import argparse
import json
import math
import os
from pathlib import Path

import h5py
import numpy as np
import robosuite

import robocasa  # noqa: F401


NAVGEN_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATASET = str(NAVGEN_ROOT / "datasets/official/NavigateKitchen/demo.hdf5")
DEFAULT_OUTPUT = str(NAVGEN_ROOT / "metrics/phase_a/baseline_openloop_10.json")


def _demo_sort_key(name: str):
    if name.startswith("demo_"):
        suffix = name.split("demo_", 1)[1]
        if suffix.isdigit():
            return (0, int(suffix))
    return (1, name)


def _angle_diff(a, b):
    d = a - b
    return (d + np.pi) % (2 * np.pi) - np.pi


def get_env_metadata_from_dataset(dataset_path: str):
    with h5py.File(os.path.expanduser(dataset_path), "r") as f:
        return json.loads(f["data"].attrs["env_args"])


def reset_to(env, state):
    if "model" in state:
        ep_meta = json.loads(state.get("ep_meta", "{}"))
        if hasattr(env, "set_attrs_from_ep_meta"):
            env.set_attrs_from_ep_meta(ep_meta)
        elif hasattr(env, "set_ep_meta"):
            env.set_ep_meta(ep_meta)

        env.reset()
        robosuite_version_id = int(robosuite.__version__.split(".")[1])
        if robosuite_version_id <= 3:
            from robosuite.utils.mjcf_utils import postprocess_model_xml

            xml = postprocess_model_xml(state["model"])
        else:
            xml = env.edit_model_xml(state["model"])

        env.reset_from_xml_string(xml)
        env.sim.reset()

    if "states" in state:
        env.sim.set_state_from_flattened(state["states"])
        env.sim.forward()

    if hasattr(env, "update_sites"):
        env.update_sites()
    if hasattr(env, "update_state"):
        env.update_state()


def _to_str(v):
    if isinstance(v, bytes):
        return v.decode("utf-8")
    return str(v)


def _get_base_pose_and_yaw(env):
    body_id = env.sim.model.body_name2id("mobilebase0_base")
    base_pos = np.array(env.sim.data.body_xpos[body_id])
    base_rot = np.array(env.sim.data.body_xmat[body_id]).reshape((3, 3))
    yaw = math.atan2(base_rot[1, 0], base_rot[0, 0])
    return base_pos, yaw


def evaluate_demo_openloop(env, demo_name: str, demo_grp):
    states = demo_grp["states"][:]
    actions = demo_grp["actions"][:]
    ep_meta_raw = demo_grp.attrs.get("ep_meta", "{}")
    model_file = demo_grp.attrs.get("model_file", None)

    if isinstance(ep_meta_raw, bytes):
        ep_meta_raw = ep_meta_raw.decode("utf-8")
    if isinstance(model_file, bytes):
        model_file = model_file.decode("utf-8")

    ep_meta = json.loads(ep_meta_raw)
    initial_state = {
        "states": states[0],
        "ep_meta": ep_meta_raw,
    }
    if model_file is not None:
        initial_state["model"] = model_file

    reset_to(env, initial_state)

    divergence_step = None
    max_state_error = 0.0
    final_state_error = 0.0

    t = actions.shape[0]
    for i in range(t):
        env.step(actions[i])
        if i < t - 1:
            playback_state = np.array(env.sim.get_state().flatten())
            err = float(np.linalg.norm(states[i + 1] - playback_state))
            max_state_error = max(max_state_error, err)
            final_state_error = err
            if divergence_step is None and err > 1e-6:
                divergence_step = i

    success = bool(env._check_success())
    target_pos = np.array(getattr(env, "target_pos", [np.nan, np.nan, np.nan]))
    target_ori = np.array(getattr(env, "target_ori", [0.0, 0.0, np.nan]))
    base_pos, base_yaw = _get_base_pose_and_yaw(env)

    final_pos_error = float(np.linalg.norm(target_pos[:2] - base_pos[:2]))
    final_yaw_error = float(abs(_angle_diff(float(target_ori[2]), float(base_yaw))))
    final_yaw_error_deg = float(np.degrees(final_yaw_error))

    fixture_refs = ep_meta.get("fixture_refs", {})
    return {
        "demo_id": demo_name,
        "traj_len": int(states.shape[0]),
        "success": success,
        "divergence_step": divergence_step,
        "max_state_error": max_state_error,
        "final_state_error": final_state_error,
        "final_pos_error": final_pos_error,
        "final_yaw_error_deg": final_yaw_error_deg,
        "layout_id": ep_meta.get("layout_id"),
        "style_id": ep_meta.get("style_id"),
        "src_fixture": fixture_refs.get("src_fixture"),
        "target_fixture": fixture_refs.get("target_fixture"),
        "lang": ep_meta.get("lang"),
    }


def summarize(results):
    n = len(results)
    succ = sum(1 for r in results if r["success"])

    def _avg(key):
        if n == 0:
            return None
        return float(sum(float(r[key]) for r in results) / n)

    divergence_steps = [
        r["divergence_step"] for r in results if r["divergence_step"] is not None
    ]
    return {
        "n_trials": n,
        "success_count": succ,
        "success_rate": float(succ / n) if n else None,
        "avg_final_pos_error": _avg("final_pos_error"),
        "avg_final_yaw_error_deg": _avg("final_yaw_error_deg"),
        "avg_max_state_error": _avg("max_state_error"),
        "divergence": {
            "count": len(divergence_steps),
            "avg_step": float(sum(divergence_steps) / len(divergence_steps))
            if divergence_steps
            else None,
            "min_step": int(min(divergence_steps)) if divergence_steps else None,
            "max_step": int(max(divergence_steps)) if divergence_steps else None,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Open-loop baseline for NavigateKitchen"
    )
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--start-index", type=int, default=0)
    args = parser.parse_args()

    env_meta = get_env_metadata_from_dataset(args.dataset)
    env_kwargs = dict(env_meta["env_kwargs"])
    env_kwargs["env_name"] = env_meta["env_name"]
    env_kwargs["has_renderer"] = False
    env_kwargs["renderer"] = "mjviewer"
    env_kwargs["has_offscreen_renderer"] = False
    env_kwargs["use_camera_obs"] = False
    env = robosuite.make(**env_kwargs)

    with h5py.File(args.dataset, "r") as f:
        demos = sorted(list(f["data"].keys()), key=_demo_sort_key)
        selected = demos[args.start_index : args.start_index + args.n]

        results = []
        for idx, demo_name in enumerate(selected):
            demo_grp = f["data"][demo_name]
            r = evaluate_demo_openloop(env=env, demo_name=demo_name, demo_grp=demo_grp)
            results.append(r)
            print(
                f"[{idx + 1}/{len(selected)}] {demo_name} "
                f"success={r['success']} pos_err={r['final_pos_error']:.3f} "
                f"yaw_err_deg={r['final_yaw_error_deg']:.2f}"
            )

    out = {
        "dataset_path": args.dataset,
        "selected_demos": selected,
        "summary": summarize(results),
        "results": results,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=True, indent=2), encoding="utf-8")

    print(f"[baseline_openloop] saved: {out_path}")
    print(
        f"[baseline_openloop] summary: {json.dumps(out['summary'], ensure_ascii=True)}"
    )


if __name__ == "__main__":
    main()
