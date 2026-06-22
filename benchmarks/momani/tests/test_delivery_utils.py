import sys
import unittest
from pathlib import Path

NAVGEN_ROOT = Path(__file__).resolve().parents[1]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from utils.delivery_utils import (  # noqa: E402
    normalize_traj_collision_threshold,
    select_delivery_subset,
)


def _record(
    demo_id,
    *,
    success=True,
    has_collision=False,
    collision_step_rate=0.0,
    final_pos_error=0.1,
):
    return {
        "demo_id": str(demo_id),
        "success": bool(success),
        "has_collision": bool(has_collision),
        "collision_step_rate": float(collision_step_rate),
        "final_pos_error": float(final_pos_error),
    }


class TestDeliveryUtils(unittest.TestCase):
    def test_normalize_traj_collision_threshold(self):
        self.assertEqual(normalize_traj_collision_threshold(0), 0.0)
        self.assertEqual(normalize_traj_collision_threshold(0.1), 0.1)
        self.assertEqual(normalize_traj_collision_threshold(0.2), 0.2)
        with self.assertRaises(ValueError):
            normalize_traj_collision_threshold(0.3)

    def test_fail_when_non_collision_not_enough_for_threshold(self):
        records = [
            *[_record(f"nc_{i}") for i in range(8)],
            *[
                _record(
                    f"c_{i}",
                    has_collision=True,
                    collision_step_rate=0.1 + i * 0.01,
                )
                for i in range(6)
            ],
        ]
        with self.assertRaises(ValueError):
            select_delivery_subset(
                records,
                target_count=10,
                traj_collision_threshold=0.1,
                success_only=True,
            )

    def test_select_subset_obeys_collision_budget(self):
        records = [
            *[_record(f"nc_{i}") for i in range(8)],
            _record("c_a", has_collision=True, collision_step_rate=0.07),
            _record("c_b", has_collision=True, collision_step_rate=0.03),
            _record("c_c", has_collision=True, collision_step_rate=0.12),
            _record("c_d", has_collision=True, collision_step_rate=0.20),
        ]
        out = select_delivery_subset(
            records,
            target_count=10,
            traj_collision_threshold=0.2,
            success_only=True,
        )
        self.assertEqual(len(out["selected_records"]), 10)
        self.assertEqual(out["selected_collision_count"], 2)
        self.assertLessEqual(out["selected_traj_collision_rate"], 0.2)
        selected_ids = [r["demo_id"] for r in out["selected_records"]]
        self.assertIn("c_b", selected_ids)
        self.assertIn("c_a", selected_ids)
        self.assertNotIn("c_c", selected_ids)

    def test_success_only_filter(self):
        records = [
            _record("ok_0", success=True, has_collision=False),
            _record("ok_1", success=True, has_collision=False),
            _record("bad_0", success=False, has_collision=False),
            _record(
                "bad_1", success=False, has_collision=True, collision_step_rate=0.1
            ),
        ]
        out = select_delivery_subset(
            records,
            target_count=2,
            traj_collision_threshold=0.0,
            success_only=True,
        )
        selected_ids = [r["demo_id"] for r in out["selected_records"]]
        self.assertEqual(selected_ids, ["ok_0", "ok_1"])


if __name__ == "__main__":
    unittest.main()
