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
from utils.collision_metrics import (
    apply_collision_gate,
    count_mobile_contacts_from_sim,
    should_trigger_collision_response,
)
from utils.hdf5_utils import (
    build_generation_schedule,
    summarize_generation_metrics,
    write_generated_dataset,
)


DEFAULT_BASE_CFG = str(NAVGEN_ROOT / "config/base_config.yaml")
DEFAULT_PHASE_B_CFG = str(NAVGEN_ROOT / "config/phase_b_control.yaml")
DEFAULT_PHASE_C_CFG = str(NAVGEN_ROOT / "config/phase_c_optimized.yaml")
DEFAULT_OUTPUT_HDF5 = str(NAVGEN_ROOT / "datasets/momani/v1/demo.hdf5")
DEFAULT_SUMMARY_JSON = str(NAVGEN_ROOT / "metrics/phase_d/generation_summary.json")
DEFAULT_FAILURES_JSONL = str(NAVGEN_ROOT / "metrics/phase_d/failure_cases.jsonl")


def _demo_sort_key(name: str):
    if name.startswith("demo_"):
        suffix = name.split("demo_", 1)[1]
        if suffix.isdigit():
            return (0, int(suffix))
    return (1, name)


def _load_yaml(path: str) -> Dict[str, Any]:
    import yaml

    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _load_geom_extra_inflation_map(path: Optional[str]) -> Dict[str, float]:
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"geom extra inflation json not found: {path}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("geom extra inflation json must be an object")
    out: Dict[str, float] = {}
    for k, v in payload.items():
        out[str(k)] = float(v)
    return out


def _yaw_from_rot(rot: np.ndarray) -> float:
    return float(math.atan2(rot[1, 0], rot[0, 0]))


def _angle_diff(a: float, b: float) -> float:
    d = a - b
    return (d + math.pi) % (2 * math.pi) - math.pi


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


def _current_base_pose_and_yaw(env) -> Tuple[np.ndarray, float]:
    body_id = env.sim.model.body_name2id("mobilebase0_base")
    base_pos = np.array(env.sim.data.body_xpos[body_id], dtype=float)
    base_rot = np.array(env.sim.data.body_xmat[body_id], dtype=float).reshape((3, 3))
    yaw = _yaw_from_rot(base_rot)
    return base_pos, yaw


def _get_base_action_slice(navigator, env) -> Tuple[int, int]:
    if navigator.mg is not None and hasattr(navigator.mg, "_get_base_action_slice"):
        bs, be = navigator.mg._get_base_action_slice()
        return int(bs), int(be)
    action_dim = int(getattr(env, "action_dim", 12))
    if action_dim >= 10:
        return 7, 10
    return max(action_dim - 3, 0), action_dim


def _generate_one_demo(
    source_demo_id: str,
    generated_demo_id: str,
    scene_manager: SceneManager,
    env,
    navigator: ClosedLoopNavigator,
    max_steps_per_demo: int,
    max_steps_per_waypoint: int,
    step_interval: int,
    waypoint_mode: str,
    geometric_segment_m: float,
    geometric_min_waypoints: int,
    geometric_max_waypoints: int,
    obstacle_grid_resolution: float,
    obstacle_inflation_m: float,
    obstacle_margin_m: float,
    semantic_handle_extra_inflation: float,
    semantic_heavy_extra_inflation: float,
    geom_extra_inflation_map: Dict[str, float],
    phase2_distance_m: float,
    final_lock_steps: int,
    runaway_window: int,
    runaway_pos_threshold_m: float,
    runaway_min_progress_m: float,
    runaway_max_events: int,
    collision_response_mode: str,
    collision_trigger_steps: int,
    collision_slowdown_scale: float,
    collision_slowdown_steps: int,
    collision_replan_backoff_m: float,
    collision_replan_to_final: bool,
    collision_max_triggers: int,
    collision_step_rate_limit: float,
) -> Dict[str, Any]:
    source_states, _ = scene_manager.read_demo_arrays(source_demo_id)
    spec = scene_manager.reset_env_to_demo_scene(
        env, source_demo_id, initial_state=source_states[0]
    )
    navigator.reset()

    if waypoint_mode in ("geometric", "geometric_to_target"):
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
    elif waypoint_mode == "obstacle_aware":
        final_target = _target_pose_from_env(env)
        if final_target is None:
            waypoints, waypoint_indices = [], []
        else:
            waypoints, waypoint_indices = (
                navigator.extract_obstacle_aware_waypoints_to_target(
                    target_pose=final_target,
                    segment_length_m=geometric_segment_m,
                    min_waypoints=geometric_min_waypoints,
                    max_waypoints=geometric_max_waypoints,
                    grid_resolution=obstacle_grid_resolution,
                    obstacle_inflation_m=obstacle_inflation_m,
                    planning_margin_m=obstacle_margin_m,
                    semantic_handle_extra_inflation=semantic_handle_extra_inflation,
                    semantic_heavy_extra_inflation=semantic_heavy_extra_inflation,
                    geom_extra_inflation_map=geom_extra_inflation_map,
                )
            )
    elif waypoint_mode == "target_only":
        final_target = _target_pose_from_env(env)
        waypoints = [final_target] if final_target is not None else []
        waypoint_indices = [-1] if final_target is not None else []
    else:
        waypoints, waypoint_indices = navigator.extract_waypoints_from_states(
            states=source_states,
            step_interval=step_interval,
        )

    final_target_pose_global = _target_pose_from_env(env)

    generated_states: List[np.ndarray] = []
    generated_actions: List[np.ndarray] = []
    rewards: List[float] = []
    dones: List[bool] = []

    generated_steps = 0
    reached_waypoints = 0
    timeout_waypoints = 0
    done_flag = False
    total_runaway_events = 0
    aborted_waypoints = 0
    collision_steps = 0
    collision_contacts_total = 0
    collision_consecutive_steps = 0
    collision_response_triggers = 0
    slowdown_steps_left = 0
    base_slice = _get_base_action_slice(navigator, env)

    for wp_idx, target_pose in enumerate(waypoints):
        local_steps = 0
        runaway_used = 0
        subtargets: List[np.ndarray] = [target_pose]
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
            action_record = np.array(full_action, dtype=np.float32, copy=True)
            if collision_response_mode == "slowdown" and slowdown_steps_left > 0:
                bs, be = base_slice
                action_record[bs:be] *= float(collision_slowdown_scale)
                slowdown_steps_left -= 1

            _, reward, done, _ = env.step(action_record)

            contact_out = count_mobile_contacts_from_sim(
                env.sim, mobile_prefix="mobilebase0"
            )
            step_contacts = int(contact_out["total_contacts"])
            collision_contacts_total += step_contacts
            if step_contacts > 0:
                collision_steps += 1
                collision_consecutive_steps += 1
            else:
                collision_consecutive_steps = 0

            sim_state = np.array(env.sim.get_state().flatten(), dtype=np.float64)
            generated_states.append(sim_state)
            generated_actions.append(action_record)
            rewards.append(float(reward))
            dones.append(bool(done))

            generated_steps += 1
            local_steps += 1
            pos_err = float(meta["pos_error"])
            reached_strict = bool(meta["reached"])

            is_final_subtarget = (wp_idx == len(waypoints) - 1) and (
                len(subtargets) == 1
            )
            reached_local = (
                reached_strict
                if is_final_subtarget
                else (pos_err <= navigator.config.reached_threshold_m)
            )

            if final_target_pose_global is not None:
                current_pose_for_global = navigator.get_current_base_pose()
                global_pos_err = float(
                    np.linalg.norm(
                        final_target_pose_global[:2, 3] - current_pose_for_global[:2, 3]
                    )
                )
            else:
                global_pos_err = pos_err
            global_err_hist.append(global_pos_err)

            if reached_local:
                subtargets.pop(0)
                if not subtargets:
                    reached_waypoints += 1
                global_err_hist.clear()
                continue

            if done:
                done_flag = True
                break

            if should_trigger_collision_response(
                consecutive_collision_steps=collision_consecutive_steps,
                trigger_steps=collision_trigger_steps,
                triggers_used=collision_response_triggers,
                max_triggers=collision_max_triggers,
            ):
                collision_response_triggers += 1
                collision_consecutive_steps = 0
                if collision_response_mode == "slowdown":
                    slowdown_steps_left = max(
                        int(slowdown_steps_left), int(collision_slowdown_steps)
                    )
                elif collision_response_mode == "replan":
                    current_pose = navigator.get_current_base_pose()
                    yaw = _yaw_from_rot(current_pose[:3, :3])
                    backoff_pose = np.array(current_pose, dtype=float)
                    backoff_dist = max(0.02, float(collision_replan_backoff_m))
                    backoff_pose[0, 3] -= backoff_dist * np.cos(yaw)
                    backoff_pose[1, 3] -= backoff_dist * np.sin(yaw)

                    if (
                        collision_replan_to_final
                        and final_target_pose_global is not None
                    ):
                        subtargets = [
                            backoff_pose,
                            np.array(final_target_pose_global, dtype=float),
                        ]
                    else:
                        subtargets.insert(0, backoff_pose)
                    global_err_hist.clear()

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
                full_action, _ = navigator.step_towards(final_target_pose)
                action_record = np.array(full_action, dtype=np.float32, copy=True)
                if collision_response_mode == "slowdown" and slowdown_steps_left > 0:
                    bs, be = base_slice
                    action_record[bs:be] *= float(collision_slowdown_scale)
                    slowdown_steps_left -= 1

                _, reward, done, _ = env.step(action_record)

                contact_out = count_mobile_contacts_from_sim(
                    env.sim, mobile_prefix="mobilebase0"
                )
                step_contacts = int(contact_out["total_contacts"])
                collision_contacts_total += step_contacts
                if step_contacts > 0:
                    collision_steps += 1

                sim_state = np.array(env.sim.get_state().flatten(), dtype=np.float64)
                generated_states.append(sim_state)
                generated_actions.append(action_record)
                rewards.append(float(reward))
                dones.append(bool(done))
                generated_steps += 1
                lock_steps += 1
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

    if success:
        stop_reason = "success"
    elif done_flag:
        stop_reason = "env_done"
    elif generated_steps >= max_steps_per_demo:
        stop_reason = "max_steps"
    elif timeout_waypoints > 0:
        stop_reason = "waypoint_timeout"
    else:
        stop_reason = "unknown"

    state_dim = int(env.sim.get_state().flatten().shape[0])
    action_dim = int(getattr(env, "action_dim", 12))

    if len(generated_states) == 0:
        states_arr = np.zeros((0, state_dim), dtype=np.float64)
        actions_arr = np.zeros((0, action_dim), dtype=np.float32)
        rewards_arr = np.zeros((0,), dtype=np.float32)
        dones_arr = np.zeros((0,), dtype=np.bool_)
    else:
        states_arr = np.asarray(generated_states, dtype=np.float64)
        actions_arr = np.asarray(generated_actions, dtype=np.float32)
        rewards_arr = np.asarray(rewards, dtype=np.float32)
        dones_arr = np.asarray(dones, dtype=np.bool_)

    stop_reason_raw = stop_reason
    if collision_step_rate_limit >= 0.0:
        gate = apply_collision_gate(
            generated_traj_len=generated_steps,
            collision_steps=collision_steps,
            success=success,
            current_stop_reason=stop_reason,
            collision_step_rate_limit=collision_step_rate_limit,
        )
        success = bool(gate["success"])
        stop_reason = str(gate["stop_reason"])

    return {
        "generated_demo_id": generated_demo_id,
        "source_demo_id": source_demo_id,
        "layout_id": spec.layout_id,
        "style_id": spec.style_id,
        "ep_meta": spec.ep_meta,
        "states": states_arr,
        "actions": actions_arr,
        "rewards": rewards_arr,
        "dones": dones_arr,
        "success": success,
        "stop_reason": stop_reason,
        "stop_reason_raw": stop_reason_raw,
        "source_traj_len": int(source_states.shape[0]),
        "generated_traj_len": int(generated_steps),
        "traj_len_ratio": float(generated_steps / max(int(source_states.shape[0]), 1)),
        "n_waypoints": int(len(waypoints)),
        "reached_waypoints": int(reached_waypoints),
        "timeout_waypoints": int(timeout_waypoints),
        "runaway_events": int(total_runaway_events),
        "aborted_waypoints": int(aborted_waypoints),
        "collision_steps": int(collision_steps),
        "collision_contacts_total": int(collision_contacts_total),
        "collision_step_rate": float(collision_steps / max(generated_steps, 1)),
        "has_collision": bool(collision_steps > 0),
        "collision_response_triggers": int(collision_response_triggers),
        "final_pos_error": final_pos_error,
        "final_yaw_error_deg": final_yaw_error_deg,
        "generation_meta": {
            "waypoint_mode": waypoint_mode,
            "geometric_segment_m": geometric_segment_m,
            "phase2_distance_m": phase2_distance_m,
            "final_lock_steps": final_lock_steps,
            "obstacle_grid_resolution": obstacle_grid_resolution,
            "obstacle_inflation_m": obstacle_inflation_m,
            "obstacle_margin_m": obstacle_margin_m,
            "collision_step_rate_limit": collision_step_rate_limit,
            "runaway_window": runaway_window,
            "runaway_pos_threshold_m": runaway_pos_threshold_m,
            "runaway_min_progress_m": runaway_min_progress_m,
            "runaway_max_events": runaway_max_events,
            "collision_response_mode": collision_response_mode,
            "collision_trigger_steps": collision_trigger_steps,
            "collision_slowdown_scale": collision_slowdown_scale,
            "collision_slowdown_steps": collision_slowdown_steps,
            "collision_replan_backoff_m": collision_replan_backoff_m,
            "collision_replan_to_final": collision_replan_to_final,
            "collision_max_triggers": collision_max_triggers,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Phase D batch generation")
    parser.add_argument("--base-config", default=DEFAULT_BASE_CFG)
    parser.add_argument("--phase-b-config", default=DEFAULT_PHASE_B_CFG)
    parser.add_argument("--phase-c-config", default=DEFAULT_PHASE_C_CFG)
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-hdf5", default=DEFAULT_OUTPUT_HDF5)
    parser.add_argument("--summary-output", default=DEFAULT_SUMMARY_JSON)
    parser.add_argument("--failures-output", default=DEFAULT_FAILURES_JSONL)

    parser.add_argument(
        "--waypoint-mode",
        default=None,
        choices=[
            "source_states",
            "geometric",
            "geometric_to_target",
            "obstacle_aware",
            "target_only",
        ],
    )
    parser.add_argument("--geometric-segment-m", type=float, default=0.7)
    parser.add_argument("--geometric-min-waypoints", type=int, default=3)
    parser.add_argument("--geometric-max-waypoints", type=int, default=10)
    parser.add_argument("--obstacle-grid-resolution", type=float, default=0.10)
    parser.add_argument("--obstacle-inflation-m", type=float, default=0.18)
    parser.add_argument("--obstacle-margin-m", type=float, default=0.8)
    parser.add_argument("--semantic-handle-extra-inflation", type=float, default=0.0)
    parser.add_argument("--semantic-heavy-extra-inflation", type=float, default=0.0)
    parser.add_argument(
        "--geom-extra-inflation-json",
        type=str,
        default=None,
        help="JSON file path: {geom_name: extra_inflation_m}",
    )
    parser.add_argument("--phase2-distance-m", type=float, default=0.7)
    parser.add_argument("--final-lock-steps", type=int, default=220)

    parser.add_argument("--runaway-window", type=int, default=25)
    parser.add_argument("--runaway-pos-threshold-m", type=float, default=5.0)
    parser.add_argument("--runaway-min-progress-m", type=float, default=0.005)
    parser.add_argument("--runaway-max-events", type=int, default=1)
    parser.add_argument(
        "--collision-response-mode",
        type=str,
        choices=["none", "slowdown", "replan"],
        default="none",
    )
    parser.add_argument("--collision-trigger-steps", type=int, default=2)
    parser.add_argument("--collision-slowdown-scale", type=float, default=0.6)
    parser.add_argument("--collision-slowdown-steps", type=int, default=8)
    parser.add_argument("--collision-replan-backoff-m", type=float, default=0.2)
    parser.add_argument("--collision-replan-to-final", action="store_true")
    parser.add_argument("--collision-max-triggers", type=int, default=1)
    parser.add_argument(
        "--collision-step-rate-limit",
        type=float,
        default=None,
        help="If >=0, mark demo failed when collision_step_rate exceeds this threshold. Example: 0.05",
    )

    args = parser.parse_args()

    base_cfg = _load_yaml(args.base_config)
    phase_b_cfg = _load_yaml(args.phase_b_config)
    phase_c_cfg = _load_yaml(args.phase_c_config)

    dataset_path = args.dataset or base_cfg.get("paths", {}).get(
        "official_dataset_hdf5"
    )
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
        args.geometric_segment_m
        if args.geometric_segment_m is not None
        else phase_b_cfg.get("waypoint", {}).get("geometric_segment_m", 0.7)
    )
    geometric_min_waypoints = int(
        args.geometric_min_waypoints
        if args.geometric_min_waypoints is not None
        else phase_b_cfg.get("waypoint", {}).get("geometric_min_waypoints", 3)
    )
    geometric_max_waypoints = int(
        args.geometric_max_waypoints
        if args.geometric_max_waypoints is not None
        else phase_b_cfg.get("waypoint", {}).get("geometric_max_waypoints", 10)
    )

    use_mg = bool(
        phase_b_cfg.get("controller", {}).get("use_mg_navigate_interface", True)
    )

    cfg_collision_limit = phase_b_cfg.get("collision_gate", {}).get(
        "collision_step_rate_limit", -1.0
    )
    collision_step_rate_limit = (
        float(args.collision_step_rate_limit)
        if args.collision_step_rate_limit is not None
        else float(cfg_collision_limit)
    )
    geom_extra_inflation_map = _load_geom_extra_inflation_map(
        args.geom_extra_inflation_json
    )

    scene_manager = SceneManager(dataset_path)
    env = scene_manager.build_env(force_offscreen=False)
    mg_interface = _try_build_mg_interface(env, enabled=use_mg)
    nav_cfg = ClosedLoopConfig.from_dicts(phase_b=phase_b_cfg, phase_c=phase_c_cfg)
    navigator = ClosedLoopNavigator(env=env, mg_interface=mg_interface, config=nav_cfg)

    import json as _json

    demo_ids = scene_manager.list_demo_ids()
    env_args_raw = _json.dumps(scene_manager.backend.get_env_meta())

    source_pool = demo_ids[args.start_index :]
    if len(source_pool) == 0:
        raise ValueError("start-index 超出 source demos 范围")

    schedule = build_generation_schedule(
        source_pool, target_count=args.n, seed=args.seed
    )

    generated: List[Dict[str, Any]] = []
    for idx, source_demo_id in enumerate(schedule):
        generated_demo_id = f"demo_{idx}"
        out = _generate_one_demo(
            source_demo_id=source_demo_id,
            generated_demo_id=generated_demo_id,
            scene_manager=scene_manager,
            env=env,
            navigator=navigator,
            max_steps_per_demo=max_steps_per_demo,
            max_steps_per_waypoint=max_steps_per_waypoint,
            step_interval=step_interval,
            waypoint_mode=waypoint_mode,
            geometric_segment_m=geometric_segment_m,
            geometric_min_waypoints=geometric_min_waypoints,
            geometric_max_waypoints=geometric_max_waypoints,
            obstacle_grid_resolution=args.obstacle_grid_resolution,
            obstacle_inflation_m=args.obstacle_inflation_m,
            obstacle_margin_m=args.obstacle_margin_m,
            semantic_handle_extra_inflation=args.semantic_handle_extra_inflation,
            semantic_heavy_extra_inflation=args.semantic_heavy_extra_inflation,
            geom_extra_inflation_map=geom_extra_inflation_map,
            phase2_distance_m=args.phase2_distance_m,
            final_lock_steps=args.final_lock_steps,
            runaway_window=args.runaway_window,
            runaway_pos_threshold_m=args.runaway_pos_threshold_m,
            runaway_min_progress_m=args.runaway_min_progress_m,
            runaway_max_events=args.runaway_max_events,
            collision_response_mode=args.collision_response_mode,
            collision_trigger_steps=args.collision_trigger_steps,
            collision_slowdown_scale=args.collision_slowdown_scale,
            collision_slowdown_steps=args.collision_slowdown_steps,
            collision_replan_backoff_m=args.collision_replan_backoff_m,
            collision_replan_to_final=args.collision_replan_to_final,
            collision_max_triggers=args.collision_max_triggers,
            collision_step_rate_limit=collision_step_rate_limit,
        )
        generated.append(out)
        print(
            f"[{idx + 1}/{len(schedule)}] src={source_demo_id} "
            f"success={out['success']} pos_err={out['final_pos_error']:.3f} "
            f"yaw_err={out['final_yaw_error_deg']:.2f} len={out['generated_traj_len']}"
        )

    write_generated_dataset(
        output_hdf5_path=args.output_hdf5,
        demos=generated,
        env_args_raw=env_args_raw,
    )

    summary = summarize_generation_metrics(generated)
    summary["target_count"] = int(args.n)
    summary["source_pool_size"] = int(len(source_pool))
    summary["dataset_path"] = dataset_path
    summary["output_hdf5"] = args.output_hdf5
    summary["config"] = {
        "waypoint_mode": waypoint_mode,
        "geometric_segment_m": geometric_segment_m,
        "geometric_min_waypoints": geometric_min_waypoints,
        "geometric_max_waypoints": geometric_max_waypoints,
        "obstacle_grid_resolution": args.obstacle_grid_resolution,
        "obstacle_inflation_m": args.obstacle_inflation_m,
        "obstacle_margin_m": args.obstacle_margin_m,
        "semantic_handle_extra_inflation": args.semantic_handle_extra_inflation,
        "semantic_heavy_extra_inflation": args.semantic_heavy_extra_inflation,
        "geom_extra_inflation_json": args.geom_extra_inflation_json,
        "geom_extra_inflation_count": int(len(geom_extra_inflation_map)),
        "phase2_distance_m": args.phase2_distance_m,
        "final_lock_steps": args.final_lock_steps,
        "runaway_window": args.runaway_window,
        "runaway_pos_threshold_m": args.runaway_pos_threshold_m,
        "runaway_min_progress_m": args.runaway_min_progress_m,
        "runaway_max_events": args.runaway_max_events,
        "collision_response_mode": args.collision_response_mode,
        "collision_trigger_steps": args.collision_trigger_steps,
        "collision_slowdown_scale": args.collision_slowdown_scale,
        "collision_slowdown_steps": args.collision_slowdown_steps,
        "collision_replan_backoff_m": args.collision_replan_backoff_m,
        "collision_replan_to_final": args.collision_replan_to_final,
        "collision_max_triggers": args.collision_max_triggers,
        "collision_step_rate_limit": collision_step_rate_limit,
        "max_steps_per_demo": max_steps_per_demo,
        "max_steps_per_waypoint": max_steps_per_waypoint,
    }

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8"
    )

    failures_path = Path(args.failures_output)
    failures_path.parent.mkdir(parents=True, exist_ok=True)
    with failures_path.open("w", encoding="utf-8") as f:
        for row in summary.get("failure_cases", []):
            f.write(json.dumps(row, ensure_ascii=True) + "\n")

    print(f"[batch_generate] hdf5: {args.output_hdf5}")
    print(f"[batch_generate] summary: {summary_path}")
    print(f"[batch_generate] failures: {failures_path}")
    print(
        f"[batch_generate] success_rate={summary.get('success_rate')} "
        f"success_count={summary.get('success_count')}/{summary.get('total_demos')}"
    )


if __name__ == "__main__":
    main()
