import sys
import unittest
from pathlib import Path

NAVGEN_ROOT = Path(__file__).resolve().parents[1]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from utils.collision_metrics import should_trigger_collision_response


class TestCollisionReactionLogic(unittest.TestCase):
    def test_trigger_when_threshold_reached_and_quota_available(self):
        self.assertTrue(
            should_trigger_collision_response(
                consecutive_collision_steps=2,
                trigger_steps=2,
                triggers_used=0,
                max_triggers=1,
            )
        )

    def test_not_trigger_when_quota_exhausted(self):
        self.assertFalse(
            should_trigger_collision_response(
                consecutive_collision_steps=5,
                trigger_steps=2,
                triggers_used=1,
                max_triggers=1,
            )
        )

    def test_not_trigger_when_below_threshold(self):
        self.assertFalse(
            should_trigger_collision_response(
                consecutive_collision_steps=1,
                trigger_steps=2,
                triggers_used=0,
                max_triggers=1,
            )
        )


if __name__ == "__main__":
    unittest.main()
