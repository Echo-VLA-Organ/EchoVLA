from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .obstacle_waypoint_planner import extract_scene_obstacles, plan_2d_path


def _angle_diff(a: float, b: float) -> float:
    d = a - b
    return (d + np.pi) % (2 * np.pi) - np.pi


def _yaw_from_rot(rot: np.ndarray) -> float:
    return float(np.arctan2(rot[1, 0], rot[0, 0]))


def _pose_from_pos_rot(pos: np.ndarray, rot: np.ndarray) -> np.ndarray:
    pose = np.eye(4, dtype=float)
    pose[:3, :3] = rot
    pose[:3, 3] = pos
    return pose


def _pose_from_pos_yaw(pos: np.ndarray, yaw: float) -> np.ndarray:
    c = np.cos(yaw)
    s = np.sin(yaw)
    rot = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=float)
    return _pose_from_pos_rot(pos=np.array(pos, dtype=float), rot=rot)


def map_base_action_for_env(
    base_action: np.ndarray,
    order: Sequence[int] = (1, 0, 2),
    sign: Sequence[float] = (1.0, 1.0, 1.0),
) -> np.ndarray:
    """Map logical [vx, vy, wz] to env expected base action order/sign."""
    logical = np.array(base_action, dtype=float).reshape(-1)
    if logical.size < 3:
        raise ValueError("base_action must have at least 3 values")

    order_arr = np.array(order, dtype=int).reshape(-1)
    sign_arr = np.array(sign, dtype=float).reshape(-1)
    if order_arr.size != 3 or sign_arr.size != 3:
        raise ValueError("order and sign must have 3 values")
    if np.any(order_arr < 0) or np.any(order_arr > 2):
        raise ValueError("order values must be in [0, 1, 2]")

    mapped = logical[order_arr] * sign_arr
    return mapped


@dataclass
class ClosedLoopConfig:
    base_mode_value: float = 1.0
    reached_threshold_m: float = 0.15
    reached_yaw_deg: float = 12.0
    clip_action_low: float = -1.0
    clip_action_high: float = 1.0
    vx_max: float = 0.80
    vy_max: float = 0.60
    wz_max: float = 1.20

    error_gate_enabled: bool = True
    ori_priority_threshold_deg: float = 17.0
    pos_priority_threshold_m: float = 0.50
    yaw_only_linear_scale: float = 0.0
    pos_mode_yaw_scale: float = 0.10

    smoothing_enabled: bool = True
    smoothing_alpha: float = 0.30

    deceleration_enabled: bool = True
    deceleration_distance_threshold_m: float = 0.50
    deceleration_min_speed_ratio: float = 0.20

    waypoint_step_interval: int = 10
    waypoint_min_interval: int = 5
    waypoint_max_interval: int = 20

    base_action_order: Tuple[int, int, int] = (1, 0, 2)
    base_action_sign: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    use_mg_target_to_action: bool = False

    @classmethod
    def from_dicts(
        cls,
        phase_b: Optional[Dict[str, Any]] = None,
        phase_c: Optional[Dict[str, Any]] = None,
    ) -> "ClosedLoopConfig":
        cfg = cls()
        phase_b = phase_b or {}
        phase_c = phase_c or {}

        b_controller = phase_b.get("controller", {})
        b_limits = phase_b.get("limits", {})
        b_waypoint = phase_b.get("waypoint", {})

        cfg.base_mode_value = float(
            b_controller.get("base_mode_value", cfg.base_mode_value)
        )
        cfg.reached_threshold_m = float(
            b_controller.get("reached_threshold_m", cfg.reached_threshold_m)
        )
        cfg.reached_yaw_deg = float(
            b_controller.get("reached_yaw_deg", cfg.reached_yaw_deg)
        )

        clip_action = b_limits.get(
            "clip_action", [cfg.clip_action_low, cfg.clip_action_high]
        )
        if isinstance(clip_action, Sequence) and len(clip_action) == 2:
            cfg.clip_action_low = float(clip_action[0])
            cfg.clip_action_high = float(clip_action[1])
        cfg.vx_max = float(b_limits.get("vx_max", cfg.vx_max))
        cfg.vy_max = float(b_limits.get("vy_max", cfg.vy_max))
        cfg.wz_max = float(b_limits.get("wz_max", cfg.wz_max))

        cfg.waypoint_step_interval = int(
            b_waypoint.get("step_interval", cfg.waypoint_step_interval)
        )
        cfg.waypoint_min_interval = int(
            b_waypoint.get("min_interval", cfg.waypoint_min_interval)
        )
        cfg.waypoint_max_interval = int(
            b_waypoint.get("max_interval", cfg.waypoint_max_interval)
        )

        order = b_controller.get("base_action_order", cfg.base_action_order)
        if isinstance(order, Sequence) and len(order) == 3:
            cfg.base_action_order = (int(order[0]), int(order[1]), int(order[2]))

        sign = b_controller.get("base_action_sign", cfg.base_action_sign)
        if isinstance(sign, Sequence) and len(sign) == 3:
            cfg.base_action_sign = (float(sign[0]), float(sign[1]), float(sign[2]))

        cfg.use_mg_target_to_action = bool(
            b_controller.get("use_mg_target_to_action", cfg.use_mg_target_to_action)
        )

        c_error_gate = phase_c.get("error_gate", {})
        c_vel = phase_c.get("velocity_limit", {})
        c_smoothing = phase_c.get("smoothing", {})
        c_decel = phase_c.get("deceleration", {})

        cfg.error_gate_enabled = bool(
            c_error_gate.get("enabled", cfg.error_gate_enabled)
        )
        cfg.ori_priority_threshold_deg = float(
            c_error_gate.get(
                "ori_priority_threshold_deg", cfg.ori_priority_threshold_deg
            )
        )
        cfg.pos_priority_threshold_m = float(
            c_error_gate.get("pos_priority_threshold_m", cfg.pos_priority_threshold_m)
        )
        cfg.yaw_only_linear_scale = float(
            c_error_gate.get("yaw_only_linear_scale", cfg.yaw_only_linear_scale)
        )
        cfg.pos_mode_yaw_scale = float(
            c_error_gate.get("pos_mode_yaw_scale", cfg.pos_mode_yaw_scale)
        )

        if c_vel.get("enabled", False):
            cfg.vx_max = float(c_vel.get("vx_max", cfg.vx_max))
            cfg.vy_max = float(c_vel.get("vy_max", cfg.vy_max))
            cfg.wz_max = float(c_vel.get("wz_max", cfg.wz_max))

        cfg.smoothing_enabled = bool(c_smoothing.get("enabled", cfg.smoothing_enabled))
        cfg.smoothing_alpha = float(c_smoothing.get("alpha", cfg.smoothing_alpha))

        cfg.deceleration_enabled = bool(
            c_decel.get("enabled", cfg.deceleration_enabled)
        )
        cfg.deceleration_distance_threshold_m = float(
            c_decel.get(
                "distance_threshold_m",
                cfg.deceleration_distance_threshold_m,
            )
        )
        cfg.deceleration_min_speed_ratio = float(
            c_decel.get("min_speed_ratio", cfg.deceleration_min_speed_ratio)
        )

        return cfg


class ClosedLoopNavigator:
    """闭环 base 导航控制器（面向 NavigateKitchen）。"""

    def __init__(
        self,
        env: Any,
        mg_interface: Optional[Any] = None,
        config: Optional[ClosedLoopConfig] = None,
    ):
        self.env = env
        self.mg = mg_interface
        self.config = config or ClosedLoopConfig()
        self._prev_base_action = np.zeros(3, dtype=float)

    def reset(self):
        self._prev_base_action = np.zeros(3, dtype=float)

    def get_current_base_pose(self) -> np.ndarray:
        body_id = self.env.sim.model.body_name2id("mobilebase0_base")
        pos = np.array(self.env.sim.data.body_xpos[body_id], dtype=float)
        rot = np.array(self.env.sim.data.body_xmat[body_id], dtype=float).reshape(
            (3, 3)
        )
        return _pose_from_pos_rot(pos, rot)

    def state_to_base_pose(self, state: np.ndarray) -> np.ndarray:
        current_state = np.array(self.env.sim.get_state().flatten())
        self.env.sim.set_state_from_flattened(state)
        self.env.sim.forward()
        pose = self.get_current_base_pose()
        self.env.sim.set_state_from_flattened(current_state)
        self.env.sim.forward()
        return pose

    def extract_waypoint_indices(
        self, traj_len: int, step_interval: Optional[int] = None
    ) -> List[int]:
        step = int(step_interval or self.config.waypoint_step_interval)
        step = max(
            self.config.waypoint_min_interval,
            min(self.config.waypoint_max_interval, step),
        )
        indices = list(range(0, max(traj_len - 1, 1), step))
        if traj_len > 0 and (not indices or indices[-1] != traj_len - 1):
            indices.append(traj_len - 1)
        return indices

    def extract_waypoints_from_states(
        self,
        states: np.ndarray,
        step_interval: Optional[int] = None,
    ) -> Tuple[List[np.ndarray], List[int]]:
        indices = self.extract_waypoint_indices(
            traj_len=int(states.shape[0]), step_interval=step_interval
        )
        waypoints = [self.state_to_base_pose(states[i]) for i in indices]
        return waypoints, indices

    def extract_geometric_waypoints_to_target(
        self,
        target_pose: np.ndarray,
        segment_length_m: float = 0.5,
        min_waypoints: int = 3,
        max_waypoints: int = 16,
    ) -> Tuple[List[np.ndarray], List[int]]:
        start_pose = self.get_current_base_pose()
        start_pos = np.array(start_pose[:3, 3], dtype=float)
        target_pos = np.array(target_pose[:3, 3], dtype=float)

        delta = target_pos[:2] - start_pos[:2]
        dist = float(np.linalg.norm(delta))

        seg = max(0.05, float(segment_length_m))
        n = int(np.ceil(dist / seg)) if dist > 1e-8 else 1
        n = max(int(min_waypoints), min(int(max_waypoints), n))

        if dist > 1e-6:
            travel_yaw = float(np.arctan2(delta[1], delta[0]))
        else:
            travel_yaw = _yaw_from_rot(start_pose[:3, :3])
        target_yaw = _yaw_from_rot(target_pose[:3, :3])

        waypoints: List[np.ndarray] = []
        indices: List[int] = []
        for i in range(1, n + 1):
            r = float(i / n)
            pos = (1.0 - r) * start_pos + r * target_pos
            yaw = target_yaw if i == n else travel_yaw
            waypoints.append(_pose_from_pos_yaw(pos=pos, yaw=yaw))
            indices.append(-1)

        return waypoints, indices

    def extract_obstacle_aware_waypoints_to_target(
        self,
        target_pose: np.ndarray,
        segment_length_m: float = 0.5,
        min_waypoints: int = 3,
        max_waypoints: int = 16,
        grid_resolution: float = 0.10,
        obstacle_inflation_m: float = 0.18,
        planning_margin_m: float = 0.8,
        semantic_handle_extra_inflation: float = 0.0,
        semantic_heavy_extra_inflation: float = 0.0,
        geom_extra_inflation_map: Optional[Dict[str, float]] = None,
    ) -> Tuple[List[np.ndarray], List[int]]:
        start_pose = self.get_current_base_pose()
        start_pos = np.array(start_pose[:3, 3], dtype=float)
        target_pos = np.array(target_pose[:3, 3], dtype=float)
        start_xy = start_pos[:2]
        target_xy = target_pos[:2]

        obstacles = extract_scene_obstacles(
            self.env,
            inflation_m=obstacle_inflation_m,
            semantic_handle_extra_inflation=semantic_handle_extra_inflation,
            semantic_heavy_extra_inflation=semantic_heavy_extra_inflation,
            geom_extra_inflation_map=geom_extra_inflation_map,
            mobile_prefix="mobilebase0",
        )
        path_xy = plan_2d_path(
            start_xy=start_xy,
            goal_xy=target_xy,
            obstacles=obstacles,
            resolution=grid_resolution,
            margin=planning_margin_m,
        )

        if len(path_xy) <= 1:
            return self.extract_geometric_waypoints_to_target(
                target_pose=target_pose,
                segment_length_m=segment_length_m,
                min_waypoints=min_waypoints,
                max_waypoints=max_waypoints,
            )

        # sample path nodes into bounded waypoint count
        total_dist = 0.0
        for i in range(1, len(path_xy)):
            total_dist += float(np.linalg.norm(path_xy[i] - path_xy[i - 1]))

        seg = max(0.05, float(segment_length_m))
        desired_n = int(np.ceil(total_dist / seg)) if total_dist > 1e-8 else 1
        desired_n = max(int(min_waypoints), min(int(max_waypoints), desired_n))

        if len(path_xy) - 1 <= desired_n:
            sampled_idx = list(range(1, len(path_xy)))
        else:
            raw = np.linspace(1, len(path_xy) - 1, desired_n)
            sampled_idx = sorted(set(int(round(x)) for x in raw))
            sampled_idx = [min(max(i, 1), len(path_xy) - 1) for i in sampled_idx]
            if sampled_idx[-1] != len(path_xy) - 1:
                sampled_idx[-1] = len(path_xy) - 1

        target_yaw = _yaw_from_rot(target_pose[:3, :3])
        z = float(start_pos[2])

        waypoints: List[np.ndarray] = []
        indices: List[int] = []
        for k, idx in enumerate(sampled_idx):
            p = path_xy[idx]
            pos = np.array([p[0], p[1], z], dtype=float)

            if idx == len(path_xy) - 1:
                yaw = target_yaw
            else:
                nxt = path_xy[min(idx + 1, len(path_xy) - 1)]
                dxy = nxt - p
                if np.linalg.norm(dxy) < 1e-8:
                    yaw = target_yaw
                else:
                    yaw = float(np.arctan2(dxy[1], dxy[0]))

            waypoints.append(_pose_from_pos_yaw(pos=pos, yaw=yaw))
            indices.append(-1)

        return waypoints, indices

    def _base_input_max(self) -> np.ndarray:
        if self.mg is not None and hasattr(self.mg, "_get_base_controller"):
            ctrl = self.mg._get_base_controller()
            return np.array(ctrl.input_max, dtype=float)

        if hasattr(self.env, "robots") and self.env.robots:
            ctrl = self.env.robots[0].composite_controller.get_controller("base")
            return np.array(ctrl.input_max, dtype=float)

        return np.array([1.0, 1.0, 1.0], dtype=float)

    def _target_to_base_action(self, target_pose: np.ndarray) -> np.ndarray:
        if (
            self.config.use_mg_target_to_action
            and self.mg is not None
            and hasattr(self.mg, "target_pose_to_action")
        ):
            action = np.array(
                self.mg.target_pose_to_action(target_pose), dtype=float
            ).reshape(-1)
            return action[:3]

        current_pose = self.get_current_base_pose()
        curr_pos = current_pose[:3, 3]
        curr_rot = current_pose[:3, :3]
        curr_yaw = _yaw_from_rot(curr_rot)

        target_pos = target_pose[:3, 3]
        target_yaw = _yaw_from_rot(target_pose[:3, :3])

        delta_world = np.array(
            [target_pos[0] - curr_pos[0], target_pos[1] - curr_pos[1]], dtype=float
        )
        delta_yaw = _angle_diff(target_yaw, curr_yaw)

        c = np.cos(curr_yaw)
        s = np.sin(curr_yaw)
        delta_base_x = c * delta_world[0] + s * delta_world[1]
        delta_base_y = -s * delta_world[0] + c * delta_world[1]

        dt = 1.0 / float(getattr(self.env, "control_freq", 20) or 20)
        vels = np.array(
            [delta_base_x / dt, delta_base_y / dt, delta_yaw / dt], dtype=float
        )
        input_max = self._base_input_max()
        return np.clip(vels / input_max, -1.0, 1.0)

    def _apply_error_gate(
        self, base_action: np.ndarray, pos_err: float, yaw_err_deg: float
    ) -> np.ndarray:
        if not self.config.error_gate_enabled:
            return base_action
        gated = np.array(base_action, dtype=float)
        if yaw_err_deg > self.config.ori_priority_threshold_deg:
            gated[0] *= self.config.yaw_only_linear_scale
            gated[1] *= self.config.yaw_only_linear_scale
        elif pos_err > self.config.pos_priority_threshold_m:
            gated[2] *= self.config.pos_mode_yaw_scale
        return gated

    def _apply_velocity_limit(self, base_action: np.ndarray) -> np.ndarray:
        input_max = self._base_input_max()
        vel = np.array(base_action, dtype=float) * input_max
        vel[0] = np.clip(vel[0], -self.config.vx_max, self.config.vx_max)
        vel[1] = np.clip(vel[1], -self.config.vy_max, self.config.vy_max)
        vel[2] = np.clip(vel[2], -self.config.wz_max, self.config.wz_max)
        return np.divide(
            vel, input_max, out=np.zeros_like(vel), where=np.abs(input_max) > 1e-8
        )

    def _apply_deceleration(
        self, base_action: np.ndarray, pos_err: float
    ) -> np.ndarray:
        if not self.config.deceleration_enabled:
            return base_action
        th = self.config.deceleration_distance_threshold_m
        if th <= 1e-8 or pos_err >= th:
            return base_action
        ratio = max(self.config.deceleration_min_speed_ratio, pos_err / th)
        slowed = np.array(base_action, dtype=float)
        slowed[0] *= ratio
        slowed[1] *= ratio
        return slowed

    def _apply_smoothing(self, base_action: np.ndarray) -> np.ndarray:
        if not self.config.smoothing_enabled:
            self._prev_base_action = np.array(base_action, dtype=float)
            return base_action
        a = float(self.config.smoothing_alpha)
        a = min(max(a, 0.0), 1.0)
        smoothed = (
            a * np.array(base_action, dtype=float) + (1.0 - a) * self._prev_base_action
        )
        self._prev_base_action = np.array(smoothed, dtype=float)
        return smoothed

    def _compute_errors(self, target_pose: np.ndarray) -> Dict[str, float]:
        current_pose = self.get_current_base_pose()
        pos_err = float(np.linalg.norm(target_pose[:2, 3] - current_pose[:2, 3]))
        curr_yaw = _yaw_from_rot(current_pose[:3, :3])
        target_yaw = _yaw_from_rot(target_pose[:3, :3])
        yaw_err_deg = float(np.degrees(abs(_angle_diff(target_yaw, curr_yaw))))
        return {"pos_error": pos_err, "yaw_error_deg": yaw_err_deg}

    def reached_target(self, target_pose: np.ndarray) -> bool:
        errs = self._compute_errors(target_pose)
        return (
            errs["pos_error"] <= self.config.reached_threshold_m
            and errs["yaw_error_deg"] <= self.config.reached_yaw_deg
        )

    def compute_base_action(
        self, target_pose: np.ndarray
    ) -> Tuple[np.ndarray, Dict[str, float]]:
        errs = self._compute_errors(target_pose)
        base_action = self._target_to_base_action(target_pose)
        base_action = self._apply_error_gate(
            base_action, errs["pos_error"], errs["yaw_error_deg"]
        )
        base_action = self._apply_velocity_limit(base_action)
        base_action = self._apply_deceleration(base_action, errs["pos_error"])
        base_action = self._apply_smoothing(base_action)
        base_action = np.clip(
            base_action, self.config.clip_action_low, self.config.clip_action_high
        )
        return base_action, errs

    def compose_full_action(
        self, base_action: np.ndarray, gripper_action: float = 0.0
    ) -> np.ndarray:
        logical_base_action = np.array(base_action, dtype=float).reshape(-1)
        env_base_action = map_base_action_for_env(
            logical_base_action,
            order=self.config.base_action_order,
            sign=self.config.base_action_sign,
        )

        if self.mg is not None and hasattr(self.mg, "compose_action"):
            full = np.array(
                self.mg.compose_action(env_base_action, np.array([gripper_action])),
                dtype=float,
            )
        else:
            action_dim = int(getattr(self.env, "action_dim", 12))
            full = np.zeros(action_dim, dtype=float)
            if self.mg is not None and hasattr(self.mg, "_get_base_action_slice"):
                bs, be = self.mg._get_base_action_slice()
            else:
                bs, be = 7, 10
            full[bs:be] = env_base_action[: (be - bs)]

        full[-1] = self.config.base_mode_value
        return np.clip(full, self.config.clip_action_low, self.config.clip_action_high)

    def step_towards(
        self,
        target_pose: np.ndarray,
        gripper_action: float = 0.0,
    ) -> Tuple[np.ndarray, Dict[str, float]]:
        base_action, errs = self.compute_base_action(target_pose)
        full_action = self.compose_full_action(
            base_action, gripper_action=gripper_action
        )
        meta = {
            "pos_error": errs["pos_error"],
            "yaw_error_deg": errs["yaw_error_deg"],
            "base_action": base_action.tolist(),
            "reached": self.reached_target(target_pose),
        }
        return full_action, meta
