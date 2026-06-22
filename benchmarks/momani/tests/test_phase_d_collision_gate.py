import sys
import unittest
from pathlib import Path

NAVGEN_ROOT = Path(__file__).resolve().parents[1]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from utils.collision_metrics import apply_collision_gate


class TestPhaseDCollisionGate(unittest.TestCase):
    def test_collision_gate_marks_failed_when_rate_exceeds_threshold(self):
        out = apply_collision_gate(
            generated_traj_len=100,
            collision_steps=20,
            success=True,
            current_stop_reason="success",
            collision_step_rate_limit=0.05,
        )
        self.assertFalse(out["success"])
        self.assertEqual(out["stop_reason"], "collision_gate")
        self.assertAlmostEqual(out["collision_step_rate"], 0.2)

    def test_collision_gate_keeps_success_when_below_threshold(self):
        out = apply_collision_gate(
            generated_traj_len=100,
            collision_steps=2,
            success=True,
            current_stop_reason="success",
            collision_step_rate_limit=0.05,
        )
        self.assertTrue(out["success"])
        self.assertEqual(out["stop_reason"], "success")
        self.assertAlmostEqual(out["collision_step_rate"], 0.02)


if __name__ == "__main__":
    unittest.main()
