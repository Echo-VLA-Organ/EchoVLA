from typing import Any, Optional, Tuple

import numpy as np


def _angle_diff(a: float, b: float) -> float:
    d = a - b
    return (d + np.pi) % (2 * np.pi) - np.pi


def _yaw_from_rot(rot: np.ndarray) -> float:
    return float(np.arctan2(rot[1, 0], rot[0, 0]))


class MGNavigateKitchenLite:
    """Minimal MG-compatible interface used by navgen.

    This avoids a hard dependency on a custom mimicgen fork while preserving
    the subset of methods navgen calls.
    """

    def __init__(self, env: Any):
        self.env = env

    def _get_base_action_slice(self) -> Tuple[int, int]:
        try:
            split = self.env.robots[0].composite_controller._action_split_indexes
            bs, be = split["base"]
            return int(bs), int(be)
        except Exception:
            return 7, 10

    def _get_gripper_action_slice(self) -> Optional[Tuple[int, int]]:
        try:
            split = self.env.robots[0].composite_controller._action_split_indexes
            if "right_gripper" in split:
                gs, ge = split["right_gripper"]
                return int(gs), int(ge)
            if "gripper" in split:
                gs, ge = split["gripper"]
                return int(gs), int(ge)
        except Exception:
            pass
        return None

    def _get_base_controller(self):
        try:
            return self.env.robots[0].composite_controller.get_controller("base")
        except Exception:
            return None

    def _get_dt(self) -> float:
        freq = getattr(self.env, "control_freq", None)
        if freq is not None and float(freq) > 0.0:
            return 1.0 / float(freq)
        return 0.05

    def get_controller_base_pose(self) -> Tuple[np.ndarray, np.ndarray]:
        body_id = self.env.sim.model.body_name2id("mobilebase0_base")
        pos = np.array(self.env.sim.data.body_xpos[body_id], dtype=float)
        rot = np.array(self.env.sim.data.body_xmat[body_id], dtype=float).reshape(
            (3, 3)
        )
        return pos, rot

    def target_pose_to_action(self, target_pose: np.ndarray) -> np.ndarray:
        target_pose = np.array(target_pose, dtype=float)
        target_pos = target_pose[:3, 3]
        target_yaw = _yaw_from_rot(target_pose[:3, :3])

        curr_pos, curr_rot = self.get_controller_base_pose()
        curr_yaw = _yaw_from_rot(curr_rot)

        delta_world = np.array(
            [target_pos[0] - curr_pos[0], target_pos[1] - curr_pos[1]], dtype=float
        )
        delta_yaw = _angle_diff(target_yaw, curr_yaw)

        c = np.cos(curr_yaw)
        s = np.sin(curr_yaw)
        delta_base_x = c * delta_world[0] + s * delta_world[1]
        delta_base_y = -s * delta_world[0] + c * delta_world[1]

        dt = self._get_dt()
        vels = np.array(
            [delta_base_x / dt, delta_base_y / dt, delta_yaw / dt], dtype=float
        )

        ctrl = self._get_base_controller()
        if ctrl is not None and hasattr(ctrl, "input_max"):
            input_max = np.array(ctrl.input_max, dtype=float)
        else:
            input_max = np.array([1.0, 1.0, 1.0], dtype=float)
        action = np.divide(
            vels,
            input_max,
            out=np.zeros_like(vels),
            where=np.abs(input_max) > 1e-8,
        )
        return np.clip(action, -1.0, 1.0)

    def compose_action(
        self, action_pose: np.ndarray, gripper_action: np.ndarray
    ) -> np.ndarray:
        action_dim = int(getattr(self.env, "action_dim", 12))
        full = np.zeros(action_dim, dtype=float)

        bs, be = self._get_base_action_slice()
        ba = np.array(action_pose, dtype=float).reshape(-1)
        full[bs:be] = ba[: max(0, be - bs)]

        gripper_slice = self._get_gripper_action_slice()
        if gripper_slice is not None:
            gs, ge = gripper_slice
            ga = np.array(gripper_action, dtype=float).reshape(-1)
            if ga.size == (ge - gs):
                full[gs:ge] = ga
            elif ga.size == 1:
                full[gs:ge] = ga[0]

        return np.clip(full, -1.0, 1.0)
