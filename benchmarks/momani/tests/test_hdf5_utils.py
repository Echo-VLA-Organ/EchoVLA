import sys
import unittest
from pathlib import Path

NAVGEN_ROOT = Path(__file__).resolve().parents[1]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from utils.hdf5_utils import build_generation_schedule, summarize_generation_metrics


class TestHdf5Utils(unittest.TestCase):
    def test_build_generation_schedule_is_deterministic(self):
        demos = ["demo_0", "demo_1", "demo_2", "demo_3"]
        s1 = build_generation_schedule(demos, target_count=9, seed=123)
        s2 = build_generation_schedule(demos, target_count=9, seed=123)
        self.assertEqual(s1, s2)
        self.assertEqual(len(s1), 9)
        for item in s1:
            self.assertIn(item, demos)

    def test_summarize_generation_metrics_counts_success(self):
        metrics = [
            {
                "success": True,
                "final_pos_error": 0.1,
                "final_yaw_error_deg": 1.0,
                "generated_traj_len": 100,
                "layout_id": 0,
                "stop_reason": "success",
                "collision_steps": 5,
                "has_collision": True,
            },
            {
                "success": False,
                "final_pos_error": 1.2,
                "final_yaw_error_deg": 8.0,
                "generated_traj_len": 200,
                "layout_id": 0,
                "stop_reason": "max_steps",
                "collision_steps": 50,
                "has_collision": True,
            },
            {
                "success": True,
                "final_pos_error": 0.2,
                "final_yaw_error_deg": 2.0,
                "generated_traj_len": 150,
                "layout_id": 1,
                "stop_reason": "success",
                "collision_steps": 0,
                "has_collision": False,
            },
        ]
        out = summarize_generation_metrics(metrics)
        self.assertEqual(out["total_demos"], 3)
        self.assertEqual(out["success_count"], 2)
        self.assertAlmostEqual(out["success_rate"], 2.0 / 3.0)
        self.assertEqual(out["stop_reason_breakdown"]["max_steps"], 1)
        self.assertAlmostEqual(out["collision_step_rate"], 55.0 / 450.0)
        self.assertAlmostEqual(out["traj_collision_rate"], 2.0 / 3.0)


if __name__ == "__main__":
    unittest.main()
