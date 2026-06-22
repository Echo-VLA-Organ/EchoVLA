import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import h5py
except ImportError:
    h5py = None

import numpy as np

NAVGEN_ROOT = Path(__file__).resolve().parents[1]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from utils.hdf5_utils import write_generated_dataset  # noqa: E402


def _load_deliver_module():
    mod_path = NAVGEN_ROOT / "scripts" / "phase_d" / "deliver_dataset.py"
    spec = importlib.util.spec_from_file_location("deliver_dataset", mod_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _demo(
    source_id,
    *,
    success,
    collision_steps,
    traj_len=10,
    final_pos_error=0.1,
):
    states = np.zeros((traj_len, 4), dtype=np.float64)
    actions = np.zeros((traj_len, 3), dtype=np.float32)
    rewards = np.zeros((traj_len,), dtype=np.float32)
    dones = np.zeros((traj_len,), dtype=np.bool_)
    return {
        "source_demo_id": source_id,
        "layout_id": 0,
        "style_id": 0,
        "ep_meta": {},
        "states": states,
        "actions": actions,
        "rewards": rewards,
        "dones": dones,
        "success": bool(success),
        "stop_reason": "success" if success else "waypoint_timeout",
        "final_pos_error": float(final_pos_error),
        "final_yaw_error_deg": 0.0,
        "collision_steps": int(collision_steps),
        "collision_step_rate": float(collision_steps / max(traj_len, 1)),
        "has_collision": bool(collision_steps > 0),
        "generation_meta": {},
    }


@unittest.skipUnless(h5py is not None, "h5py not installed")
class TestPhaseDDeliverDataset(unittest.TestCase):
    def test_deliver_threshold_zero(self):
        mod = _load_deliver_module()
        with tempfile.TemporaryDirectory() as td:
            input_hdf5 = Path(td) / "in.hdf5"
            output_hdf5 = Path(td) / "out.hdf5"
            summary_json = Path(td) / "summary.json"

            demos = [
                _demo("s0", success=True, collision_steps=0),
                _demo("s1", success=True, collision_steps=0),
                _demo("s2", success=True, collision_steps=0),
                _demo("s3", success=True, collision_steps=0),
                _demo("s4", success=True, collision_steps=2),
                _demo("s5", success=True, collision_steps=3),
            ]
            write_generated_dataset(str(input_hdf5), demos, env_args_raw=json.dumps({}))

            summary = mod.deliver_dataset(
                input_hdf5=str(input_hdf5),
                output_hdf5=str(output_hdf5),
                target_count=4,
                traj_collision_threshold=0.0,
                success_only=True,
                summary_output=str(summary_json),
                dry_run=False,
            )

            self.assertEqual(summary["selected_count"], 4)
            self.assertEqual(summary["selected_traj_collision_rate"], 0.0)
            self.assertTrue(output_hdf5.exists())

            with h5py.File(output_hdf5, "r") as f:
                self.assertEqual(len(f["data"].keys()), 4)

    def test_deliver_strict_fail_when_short(self):
        mod = _load_deliver_module()
        with tempfile.TemporaryDirectory() as td:
            input_hdf5 = Path(td) / "in.hdf5"
            output_hdf5 = Path(td) / "out.hdf5"
            summary_json = Path(td) / "summary.json"

            demos = [
                _demo("s0", success=True, collision_steps=0),
                _demo("s1", success=True, collision_steps=1),
                _demo("s2", success=True, collision_steps=2),
                _demo("s3", success=False, collision_steps=0),
            ]
            write_generated_dataset(str(input_hdf5), demos, env_args_raw=json.dumps({}))

            with self.assertRaises(ValueError):
                mod.deliver_dataset(
                    input_hdf5=str(input_hdf5),
                    output_hdf5=str(output_hdf5),
                    target_count=3,
                    traj_collision_threshold=0.0,
                    success_only=True,
                    summary_output=str(summary_json),
                    dry_run=False,
                )


if __name__ == "__main__":
    unittest.main()
