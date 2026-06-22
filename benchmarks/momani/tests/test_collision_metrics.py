import sys
import unittest
from pathlib import Path

NAVGEN_ROOT = Path(__file__).resolve().parents[1]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from utils.collision_metrics import (
    count_mobile_contacts,
    count_mobile_contacts_from_pairs,
)


class TestCollisionMetrics(unittest.TestCase):
    def test_count_mobile_contacts_only_counts_mobile_vs_non_mobile(self):
        contact_pairs = [
            ("mobilebase0_pedestal_feet_col", "stack_handle"),
            ("mobilebase0_pedestal_feet_col", "mobilebase0_wheel_col"),
            ("counter_top", "stack_handle"),
        ]
        out = count_mobile_contacts(contact_pairs, mobile_prefix="mobilebase0")
        self.assertEqual(out, 1)

    def test_count_mobile_contacts_from_pairs_tracks_unique_and_total(self):
        contact_pairs = [
            ("mobilebase0_pedestal_feet_col", "dishwasher_main_group_g2"),
            ("mobilebase0_pedestal_feet_col", "dishwasher_main_group_g2"),
            ("mobilebase0_pedestal_feet_col", "fridge_housing_left_group_right"),
            ("counter_top", "stack_handle"),
        ]
        out = count_mobile_contacts_from_pairs(
            contact_pairs, mobile_prefix="mobilebase0"
        )
        self.assertEqual(out["total_contacts"], 3)
        self.assertEqual(out["unique_target_geoms"], 2)


if __name__ == "__main__":
    unittest.main()
