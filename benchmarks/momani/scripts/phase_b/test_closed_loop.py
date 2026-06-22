#!/usr/bin/env python3

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

NAVGEN_ROOT = Path(__file__).resolve().parents[2]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from controllers import ClosedLoopConfig, ClosedLoopNavigator
from data_gen import SceneManager


DEFAULT_BASE_CFG = str(NAVGEN_ROOT / "config/base_config.yaml")
DEFAULT_PHASE_B_CFG = str(NAVGEN_ROOT / "config/phase_b_control.yaml")
DEFAULT_PHASE_C_CFG = str(NAVGEN_ROOT / "config/phase_c_optimized.yaml")
DEFAULT_OUTPUT = str(NAVGEN_ROOT / "metrics/phase_b/closed_loop_eval_10.json")


def _demo_sort_key(name: str):
    if name.startswith("demo_"):
        suffix = name.split("demo_", 1)[1]
        if suffix.isdigit():
            return (0, int(suffix))
    return (1, name)


def _load_yaml(path: str) -> Dict[str, Any]:
    try:
        import yaml
    except Exception as exc:
        raise RuntimeError(
            "缺少 PyYAML 依赖，请在可用环境安装后重试（建议使用 uv 或项目 .venv）。"
        ) from exc

    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _yaw_from_rot(rot: np.ndarray) -> float:
    return float(math.atan2(rot[1, 0], rot[0, 0]))


def _angle_diff(a: float, b: float) -> float:
    d = a - b
    return (d + math.pi) % (2 * math.pi) - math.pi


def _current_base_pose_and_yaw(env) -> Tuple[np.ndarray, float]:
    body_id = env.sim.model.body_name2id("mobilebase0_base")
    base_pos = np.array(env.sim.data.body_xpos[body_id], dtype=float)
    base_rot = np.array(env.sim.data.body_xmat[body_id], dtype=float).reshape((3, 3))
    yaw = _yaw_from_rot(base_rot)
    return base_pos, yaw


def _target_pose_from_env(env) -> Optional[np.ndarray]:
    target_pos = getattr(env, "target_pos", None)
    target_ori = getattr(env, "target_ori", None)
    if target_pos is None or target_ori is None:
        return None
    tp = np.array(target_pos, dtype=float)
    to = np.array(target_ori, dtype=float)
    yaw = float(to[2])
    c = math.cos(yaw)
    s = math.sin(yaw)
    rot = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=float)
    pose = np.eye(4, dtype=float)
    pose[:3, :3] = rot
    pose[:3, 3] = tp
    return pose


def _interpolate_pose(
    start_pose: np.ndarray, end_pose: np.ndarray, ratio: float
) -> np.ndarray:
    r = float(np.clip(ratio, 0.05, 0.95))
    out = np.array(start_pose, dtype=float)
    out[:3, 3] = (1.0 - r) * start_pose[:3, 3] + r * end_pose[:3, 3]
    syaw = _yaw_from_rot(start_pose[:3, :3])
    eyaw = _yaw_from_rot(end_pose[:3, :3])
    dyaw = _angle_diff(eyaw, syaw)
    tyaw = syaw + r * dyaw
    c = math.cos(tyaw)
    s = math.sin(tyaw)
    out[:3, :3] = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=float)
    return out


def _pose_with_yaw(pose: np.ndarray, yaw: float) -> np.ndarray:
    out = np.array(pose, dtype=float)
    c = math.cos(yaw)
    s = math.sin(yaw)
    out[:3, :3] = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=float)
    return out


def _try_build_mg_interface(env, enabled: bool):
    if not enabled:
        return None

    try:
        from controllers import MGNavigateKitchenLite

        return MGNavigateKitchenLite(env)
    except Exception:
        pass

    # Optional fallback: external mimicgen source.
    try:
        from mimicgen.env_interfaces.robocasa.single_stage.mg_navigate import (
            MG_NavigateKitchen,
        )

        return MG_NavigateKitchen(env)
    except Exception:
        pass

    candidates: List[Path] = []
    for env_name in ("NAVGEN_MIMICGEN_SRC", "MIMICGEN_SRC"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            candidates.append(Path(raw).expanduser())

    candidates.append(NAVGEN_ROOT / ".deps/mimicgen")
    candidates.append(NAVGEN_ROOT.parent / "mimicgen-robocasa")

    for p in candidates:
        rp = p.resolve()
        if rp.exists() and str(rp) not in sys.path:
            sys.path.append(str(rp))
            try:
                from mimicgen.env_interfaces.robocasa.single_stage.mg_navigate import (
                    MG_NavigateKitchen,
                )

                return MG_NavigateKitchen(env)
            except Exception:
                continue
    return None


def _evaluate_one_demo(
    demo_id: str,
    scene_manager: SceneManager,
    env,
    navigator: ClosedLoopNavigator,
    max_steps_per_demo: int,
    max_steps_per_waypoint: int,
    step_interval: int,
    save_step_trace: bool,
    final_lock_steps: int,
    target_only: bool,
    waypoint_mode: str,
    geometric_segment_m: float,
    geometric_min_waypoints: int,
    geometric_max_waypoints: int,
    phase2_distance_m: float,
    stuck_window: int,
    stuck_min_progress_m: float,
    stuck_replan_enabled: bool,
    stuck_replan_max_per_waypoint: int,
    stuck_replan_ratio: float,
    runaway_window: int,
    runaway_pos_threshold_m: float,
    runaway_min_progress_m: float,
    runaway_max_events: int,
    skip_scene_reset: bool = False,
    segment_ep_meta: Optional[Dict[str, Any]] = None,
):
    from utils.nav_stitch import apply_nav_segment_target

    if skip_scene_reset:
        spec = scene_manager.load_scene_spec(demo_id)
        if segment_ep_meta is not None:
            apply_nav_segment_target(env, segment_ep_meta)
        else:
            apply_nav_segment_target(env, spec.ep_meta)
        states = None
    else:
        states, _ = scene_manager.read_demo_arrays(demo_id)
        spec = scene_manager.reset_env_to_demo_scene(env, demo_id, initial_state=states[0])
    navigator.reset()

    if target_only:
        final_target = _target_pose_from_env(env)
        waypoints = [final_target] if final_target is not None else []
        waypoint_indices = [-1] if final_target is not None else []
    elif waypoint_mode in ("geometric", "geometric_to_target"):
        final_target = _target_pose_from_env(env)
        if final_target is None:
            waypoints, waypoint_indices = [], []
        else:
            waypoints, waypoint_indices = (
                navigator.extract_geometric_waypoints_to_target(
                    target_pose=final_target,
                    segment_length_m=geometric_segment_m,
                    min_waypoints=geometric_min_waypoints,
                    max_waypoints=geometric_max_waypoints,
                )
            )
    elif states is None:
        final_target = _target_pose_from_env(env)
        if final_target is None:
            waypoints, waypoint_indices = [], []
        else:
            waypoints, waypoint_indices = (
                navigator.extract_geometric_waypoints_to_target(
                    target_pose=final_target,
                    segment_length_m=geometric_segment_m,
                    min_waypoints=geometric_min_waypoints,
                    max_waypoints=geometric_max_waypoints,
                )
            )
    else:
        waypoints, waypoint_indices = navigator.extract_waypoints_from_states(
            states=states,
            step_interval=step_interval,
        )

    final_target_pose_global = _target_pose_from_env(env)

    generated_steps = 0
    reached_waypoints = 0
    timeout_waypoints = 0
    done_flag = False
    step_trace: List[Dict[str, Any]] = []
    total_replans = 0
    total_stuck_events = 0
    total_runaway_events = 0
    aborted_waypoints = 0

    for wp_idx, target_pose in enumerate(waypoints):
        local_steps = 0
        replan_used = 0
        runaway_used = 0
        subtargets: List[np.ndarray] = [target_pose]
        pos_err_hist: List[float] = []
        global_err_hist: List[float] = []

        while (
            subtargets
            and local_steps < max_steps_per_waypoint
            and generated_steps < max_steps_per_demo
        ):
            current_target = subtargets[0]

            current_base_pose = navigator.get_current_base_pose()
            current_base_yaw = _yaw_from_rot(current_base_pose[:3, :3])
            current_target_pos_err = float(
                np.linalg.norm(current_target[:2, 3] - current_base_pose[:2, 3])
            )
            phase = (
                "align" if current_target_pos_err <= phase2_distance_m else "translate"
            )
            effective_target = (
                current_target
                if phase == "align"
                else _pose_with_yaw(current_target, current_base_yaw)
            )

            full_action, meta = navigator.step_towards(effective_target)
            _, _, done, _ = env.step(full_action)
            generated_steps += 1
            local_steps += 1
            pos_err = float(meta["pos_error"])
            yaw_err = float(meta["yaw_error_deg"])
            if final_target_pose_global is not None:
                current_pose_for_global = navigator.get_current_base_pose()
                global_pos_err = float(
                    np.linalg.norm(
                        final_target_pose_global[:2, 3] - current_pose_for_global[:2, 3]
                    )
                )
            else:
                global_pos_err = pos_err
            reached_strict = bool(meta["reached"])
            is_final_subtarget = (wp_idx == len(waypoints) - 1) and (
                len(subtargets) == 1
            )
            reached_local = (
                reached_strict
                if is_final_subtarget
                else (pos_err <= navigator.config.reached_threshold_m)
            )
            pos_err_hist.append(pos_err)
            global_err_hist.append(global_pos_err)

            delta_pos_error_10 = None
            if len(pos_err_hist) >= 10:
                delta_pos_error_10 = float(pos_err_hist[-10] - pos_err_hist[-1])

            if save_step_trace:
                ba = np.array(meta["base_action"], dtype=float).reshape(-1)
                step_trace.append(
                    {
                        "global_step": generated_steps,
                        "waypoint_idx": wp_idx,
                        "source_state_idx": int(waypoint_indices[wp_idx]),
                        "pos_error": pos_err,
                        "global_final_pos_error": global_pos_err,
                        "yaw_error_deg": yaw_err,
                        "base_action": [float(x) for x in ba],
                        "base_action_norm": float(np.linalg.norm(ba)),
                        "phase": phase,
                        "delta_pos_error_per_10_steps": delta_pos_error_10,
                        "stuck_counter": total_stuck_events,
                        "replan_counter": total_replans,
                        "runaway_counter": total_runaway_events,
                        "reached": bool(reached_local),
                        "reached_strict": reached_strict,
                    }
                )

            if reached_local:
                subtargets.pop(0)
                if not subtargets:
                    reached_waypoints += 1
                pos_err_hist.clear()
                global_err_hist.clear()
                continue

            if done:
                done_flag = True
                break

            if (
                stuck_replan_enabled
                and stuck_window > 0
                and len(pos_err_hist) >= stuck_window
                and replan_used < stuck_replan_max_per_waypoint
            ):
                progress = float(pos_err_hist[-stuck_window] - pos_err_hist[-1])
                if progress < stuck_min_progress_m and pos_err > max(
                    0.25, navigator.config.reached_threshold_m * 1.5
                ):
                    total_stuck_events += 1
                    replan_used += 1
                    total_replans += 1
                    current_pose = navigator.get_current_base_pose()
                    mid_pose = _interpolate_pose(
                        current_pose, current_target, stuck_replan_ratio
                    )
                    subtargets.insert(0, mid_pose)
                    pos_err_hist.clear()

            if (
                runaway_window > 0
                and len(global_err_hist) >= runaway_window
                and runaway_used < runaway_max_events
            ):
                runaway_progress = float(
                    global_err_hist[-runaway_window] - global_err_hist[-1]
                )
                if (
                    runaway_progress < runaway_min_progress_m
                    and global_pos_err > runaway_pos_threshold_m
                ):
                    total_runaway_events += 1
                    runaway_used += 1
                    if final_target_pose_global is not None:
                        subtargets = [final_target_pose_global]
                    else:
                        current_pose = navigator.get_current_base_pose()
                        recovery_pose = _interpolate_pose(
                            current_pose, current_target, 0.25
                        )
                        subtargets.insert(0, recovery_pose)
                    pos_err_hist.clear()
                    global_err_hist.clear()

        if (
            subtargets
            and (not done_flag)
            and runaway_max_events > 0
            and runaway_used >= runaway_max_events
        ):
            aborted_waypoints += 1

        if subtargets and not done_flag:
            timeout_waypoints += 1

        if done_flag or generated_steps >= max_steps_per_demo:
            break

    success = bool(env._check_success())

    if (
        (not success)
        and (generated_steps < max_steps_per_demo)
        and final_lock_steps > 0
    ):
        final_target_pose = _target_pose_from_env(env)
        if final_target_pose is not None:
            lock_steps = 0
            while (
                lock_steps < final_lock_steps
                and generated_steps < max_steps_per_demo
                and (not done_flag)
                and (not navigator.reached_target(final_target_pose))
            ):
                full_action, meta = navigator.step_towards(final_target_pose)
                _, _, done, _ = env.step(full_action)
                generated_steps += 1
                lock_steps += 1
                if save_step_trace:
                    step_trace.append(
                        {
                            "global_step": generated_steps,
                            "waypoint_idx": -1,
                            "source_state_idx": -1,
                            "pos_error": float(meta["pos_error"]),
                            "yaw_error_deg": float(meta["yaw_error_deg"]),
                            "base_action": [float(x) for x in meta["base_action"]],
                            "reached": bool(meta["reached"]),
                        }
                    )
                if done:
                    done_flag = True
                    break

    success = bool(env._check_success())

    base_pos, base_yaw = _current_base_pose_and_yaw(env)
    target_pos = np.array(
        getattr(env, "target_pos", [np.nan, np.nan, np.nan]), dtype=float
    )
    target_ori = np.array(getattr(env, "target_ori", [0.0, 0.0, np.nan]), dtype=float)

    final_pos_error = float(np.linalg.norm(target_pos[:2] - base_pos[:2]))
    final_yaw_error_deg = float(
        np.degrees(abs(_angle_diff(float(target_ori[2]), base_yaw)))
    )

    stop_reason = "success" if success else "max_steps_or_timeout"
    if done_flag and not success:
        stop_reason = "env_done"

    out = {
        "demo_id": demo_id,
        "success": success,
        "stop_reason": stop_reason,
        "layout_id": spec.layout_id,
        "style_id": spec.style_id,
        "src_fixture": spec.fixture_refs.get("src_fixture"),
        "target_fixture": spec.fixture_refs.get("target_fixture"),
        "lang": spec.ep_meta.get("lang"),
        "source_traj_len": int(states.shape[0]) if states is not None else 0,
        "generated_traj_len": int(generated_steps),
        "traj_len_ratio": float(
            generated_steps / max(int(states.shape[0]) if states is not None else 1, 1)
        ),
        "n_waypoints": int(len(waypoints)),
        "reached_waypoints": int(reached_waypoints),
        "timeout_waypoints": int(timeout_waypoints),
        "stuck_events": int(total_stuck_events),
        "replan_count": int(total_replans),
        "runaway_events": int(total_runaway_events),
        "aborted_waypoints": int(aborted_waypoints),
        "final_pos_error": final_pos_error,
        "final_yaw_error_deg": final_yaw_error_deg,
    }
    if save_step_trace:
        out["step_trace"] = step_trace
    return out


def _summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(results)
    success_count = sum(1 for r in results if r["success"])

    def _avg(key: str):
        vals = [float(r[key]) for r in results if key in r]
        return float(sum(vals) / len(vals)) if vals else None

    return {
        "n_trials": n,
        "success_count": success_count,
        "success_rate": float(success_count / n) if n else None,
        "avg_final_pos_error": _avg("final_pos_error"),
        "avg_final_yaw_error_deg": _avg("final_yaw_error_deg"),
        "avg_generated_traj_len": _avg("generated_traj_len"),
        "avg_traj_len_ratio": _avg("traj_len_ratio"),
        "avg_reached_waypoints": _avg("reached_waypoints"),
        "avg_timeout_waypoints": _avg("timeout_waypoints"),
        "avg_stuck_events": _avg("stuck_events"),
        "avg_replan_count": _avg("replan_count"),
        "avg_runaway_events": _avg("runaway_events"),
        "avg_aborted_waypoints": _avg("aborted_waypoints"),
    }


def _evaluate_stitched_plan(
    plan,
    scene_manager: SceneManager,
    env,
    navigator: ClosedLoopNavigator,
    eval_kwargs: Dict[str, Any],
    max_steps_per_demo: int,
):
    segment_results = []
    steps_used = 0
    all_success = True

    for seg_idx, segment in enumerate(plan.segments):
        remaining = max(0, max_steps_per_demo - steps_used)
        if remaining <= 0:
            all_success = False
            segment_results.append(
                {
                    "segment_index": seg_idx,
                    "demo_id": segment.demo_id,
                    "lang": segment.lang,
                    "success": False,
                    "stop_reason": "budget_exhausted",
                }
            )
            continue

        spec = scene_manager.load_scene_spec(segment.demo_id)
        seg_kwargs = dict(eval_kwargs)
        seg_kwargs["max_steps_per_demo"] = remaining
        seg_kwargs["skip_scene_reset"] = seg_idx > 0
        seg_kwargs["segment_ep_meta"] = spec.ep_meta if seg_idx > 0 else None
        if seg_idx > 0:
            seg_kwargs["waypoint_mode"] = "geometric_to_target"

        result = _evaluate_one_demo(
            demo_id=segment.demo_id,
            scene_manager=scene_manager,
            env=env,
            navigator=navigator,
            **seg_kwargs,
        )
        result["segment_index"] = seg_idx
        result["lang"] = segment.lang
        segment_results.append(result)
        steps_used += int(result.get("generated_traj_len", 0))
        if not bool(result.get("success", False)):
            all_success = False
            break

    return {
        "plan_id": plan.plan_id,
        "layout_id": plan.layout_id,
        "style_id": plan.style_id,
        "stitch_length": len(plan.segments),
        "segments_completed": len(segment_results),
        "success": all_success and len(segment_results) == len(plan.segments),
        "generated_traj_len": steps_used,
        "segment_results": segment_results,
        "segment_langs": [s.lang for s in plan.segments],
    }


def main():
    parser = argparse.ArgumentParser(description="Phase B closed-loop evaluation")
    parser.add_argument("--base-config", default=DEFAULT_BASE_CFG)
    parser.add_argument("--phase-b-config", default=DEFAULT_PHASE_B_CFG)
    parser.add_argument("--phase-c-config", default=DEFAULT_PHASE_C_CFG)
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--no-step-trace", action="store_true")
    parser.add_argument("--final-lock-steps", type=int, default=150)
    parser.add_argument("--target-only", action="store_true")
    parser.add_argument(
        "--waypoint-mode",
        default=None,
        choices=["source_states", "geometric", "geometric_to_target"],
    )
    parser.add_argument("--geometric-segment-m", type=float, default=0.5)
    parser.add_argument("--geometric-min-waypoints", type=int, default=3)
    parser.add_argument("--geometric-max-waypoints", type=int, default=16)
    parser.add_argument("--phase2-distance-m", type=float, default=0.6)
    parser.add_argument("--stuck-window", type=int, default=15)
    parser.add_argument("--stuck-min-progress-m", type=float, default=0.05)
    parser.add_argument("--stuck-replan-enabled", action="store_true")
    parser.add_argument("--stuck-replan-max-per-waypoint", type=int, default=2)
    parser.add_argument("--stuck-replan-ratio", type=float, default=0.45)
    parser.add_argument("--runaway-window", type=int, default=20)
    parser.add_argument("--runaway-pos-threshold-m", type=float, default=4.0)
    parser.add_argument("--runaway-min-progress-m", type=float, default=0.01)
    parser.add_argument("--runaway-max-events", type=int, default=2)
    parser.add_argument(
        "--nav-stitch",
        action="store_true",
        help="Evaluate multi-leg nav plans (same layout, sequential targets)",
    )
    parser.add_argument(
        "--stitch-length",
        type=int,
        default=3,
        help="Number of nav legs per stitched plan (requires --nav-stitch)",
    )
    args = parser.parse_args()

    base_cfg = _load_yaml(args.base_config)
    phase_b_cfg = _load_yaml(args.phase_b_config)
    phase_c_cfg = _load_yaml(args.phase_c_config)

    dataset_path = args.dataset or base_cfg.get("paths", {}).get(
        "official_dataset_hdf5"
    ) or base_cfg.get("paths", {}).get("robocasa365_lerobot_root")
    if not dataset_path:
        raise ValueError(
            "dataset path 未提供，请传 --dataset 或在 base_config.yaml 中配置。"
        )

    max_steps_per_demo = int(
        base_cfg.get("execution", {}).get("max_steps_per_demo", 500)
    )
    max_steps_per_waypoint = int(
        phase_b_cfg.get("controller", {}).get("max_steps_per_waypoint", 50)
    )
    step_interval = int(phase_b_cfg.get("waypoint", {}).get("step_interval", 10))
    waypoint_mode = str(phase_b_cfg.get("waypoint", {}).get("mode", "source_states"))
    if waypoint_mode == "sampled_from_source_states":
        waypoint_mode = "source_states"
    if args.waypoint_mode is not None:
        waypoint_mode = args.waypoint_mode

    geometric_segment_m = float(
        phase_b_cfg.get("waypoint", {}).get("geometric_segment_m", 0.5)
    )
    geometric_min_waypoints = int(
        phase_b_cfg.get("waypoint", {}).get("geometric_min_waypoints", 3)
    )
    geometric_max_waypoints = int(
        phase_b_cfg.get("waypoint", {}).get("geometric_max_waypoints", 16)
    )

    geometric_segment_m = float(args.geometric_segment_m or geometric_segment_m)
    geometric_min_waypoints = int(
        args.geometric_min_waypoints or geometric_min_waypoints
    )
    geometric_max_waypoints = int(
        args.geometric_max_waypoints or geometric_max_waypoints
    )
    use_mg = bool(
        phase_b_cfg.get("controller", {}).get("use_mg_navigate_interface", True)
    )
    save_step_trace = bool(
        phase_b_cfg.get("logging", {}).get("save_step_level_trace", True)
    )
    if args.no_step_trace:
        save_step_trace = False

    scene_manager = SceneManager(dataset_path)
    env = scene_manager.build_env(force_offscreen=False)
    mg_interface = _try_build_mg_interface(env, enabled=use_mg)
    nav_cfg = ClosedLoopConfig.from_dicts(phase_b=phase_b_cfg, phase_c=phase_c_cfg)
    navigator = ClosedLoopNavigator(env=env, mg_interface=mg_interface, config=nav_cfg)

    eval_kwargs = dict(
        max_steps_per_waypoint=max_steps_per_waypoint,
        step_interval=step_interval,
        save_step_trace=save_step_trace,
        final_lock_steps=args.final_lock_steps,
        target_only=args.target_only,
        waypoint_mode=waypoint_mode,
        geometric_segment_m=geometric_segment_m,
        geometric_min_waypoints=geometric_min_waypoints,
        geometric_max_waypoints=geometric_max_waypoints,
        phase2_distance_m=args.phase2_distance_m,
        stuck_window=args.stuck_window,
        stuck_min_progress_m=args.stuck_min_progress_m,
        stuck_replan_enabled=args.stuck_replan_enabled,
        stuck_replan_max_per_waypoint=args.stuck_replan_max_per_waypoint,
        stuck_replan_ratio=args.stuck_replan_ratio,
        runaway_window=args.runaway_window,
        runaway_pos_threshold_m=args.runaway_pos_threshold_m,
        runaway_min_progress_m=args.runaway_min_progress_m,
        runaway_max_events=args.runaway_max_events,
    )

    results = []
    dataset_format = scene_manager.dataset_format
    print(f"[closed_loop] dataset_format={dataset_format} path={dataset_path}")

    if args.nav_stitch:
        from utils.nav_stitch import build_nav_stitch_plans

        plans = build_nav_stitch_plans(
            scene_manager.backend,
            stitch_length=args.stitch_length,
            max_plans=args.n,
            seed=int(base_cfg.get("project", {}).get("seed", 42)),
        )
        for plan in plans:
            results.append(
                _evaluate_stitched_plan(
                    plan=plan,
                    scene_manager=scene_manager,
                    env=env,
                    navigator=navigator,
                    eval_kwargs=eval_kwargs,
                    max_steps_per_demo=max_steps_per_demo,
                )
            )
        selected_demos = [r.get("plan_id") for r in results]
    else:
        demo_ids = scene_manager.list_demo_ids()
        selected = demo_ids[args.start_index : args.start_index + args.n]

        for demo_id in selected:
            results.append(
                _evaluate_one_demo(
                    demo_id=demo_id,
                    scene_manager=scene_manager,
                    env=env,
                    navigator=navigator,
                    max_steps_per_demo=max_steps_per_demo,
                    **eval_kwargs,
                )
            )
        for i, demo_id in enumerate(selected):
            r = results[i]
            print(
                f"[{i + 1}/{len(selected)}] {demo_id} "
                f"success={r['success']} "
                f"pos_err={r['final_pos_error']:.3f} "
                f"yaw_err_deg={r['final_yaw_error_deg']:.2f} "
                f"gen_len={r['generated_traj_len']}"
            )
        selected_demos = selected

    out = {
        "dataset_path": dataset_path,
        "dataset_format": dataset_format,
        "nav_stitch": bool(args.nav_stitch),
        "selected_demos": selected_demos,
        "config": {
            "max_steps_per_demo": max_steps_per_demo,
            "max_steps_per_waypoint": max_steps_per_waypoint,
            "step_interval": step_interval,
            "waypoint_mode": waypoint_mode,
            "geometric_segment_m": geometric_segment_m,
            "geometric_min_waypoints": geometric_min_waypoints,
            "geometric_max_waypoints": geometric_max_waypoints,
            "phase2_distance_m": args.phase2_distance_m,
            "use_mg_interface": mg_interface is not None,
            "save_step_trace": save_step_trace,
            "stuck_window": args.stuck_window,
            "stuck_min_progress_m": args.stuck_min_progress_m,
            "stuck_replan_enabled": args.stuck_replan_enabled,
            "stuck_replan_max_per_waypoint": args.stuck_replan_max_per_waypoint,
            "stuck_replan_ratio": args.stuck_replan_ratio,
            "runaway_window": args.runaway_window,
            "runaway_pos_threshold_m": args.runaway_pos_threshold_m,
            "runaway_min_progress_m": args.runaway_min_progress_m,
            "runaway_max_events": args.runaway_max_events,
        },
        "summary": _summarize(results),
        "results": results,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=True, indent=2), encoding="utf-8")

    print(f"[test_closed_loop] saved: {out_path}")
    print(
        f"[test_closed_loop] summary: {json.dumps(out['summary'], ensure_ascii=True)}"
    )


if __name__ == "__main__":
    main()
