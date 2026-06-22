import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.dataset_backend import (
    LeRobot365DatasetBackend,
    detect_dataset_format,
    open_dataset_backend,
)
from utils.nav_stitch import build_nav_stitch_plans


RC365_ROOT = Path(os.environ.get("ECHO_ROBOCASA365_DATA", "./data/robocasa365-datasets")).expanduser()
RC365_ROOT = RC365_ROOT / "pretrain/atomic/NavigateKitchen/20250821/lerobot"


@unittest.skipUnless(RC365_ROOT.is_dir(), "robocasa365 NavigateKitchen not available")
class TestLeRobot365Backend(unittest.TestCase):
    def test_detect_format(self):
        self.assertEqual(detect_dataset_format(RC365_ROOT), "lerobot365")

    def test_list_and_load(self):
        backend = LeRobot365DatasetBackend(RC365_ROOT)
        demo_ids = backend.list_demo_ids()
        self.assertGreater(len(demo_ids), 0)
        self.assertTrue(demo_ids[0].startswith("episode_"))

        payload = backend.load_scene_payload(demo_ids[0])
        self.assertIn("layout_id", payload["ep_meta"])
        self.assertIsNotNone(payload.get("model_xml"))

        states, actions = backend.read_demo_arrays(demo_ids[0])
        self.assertEqual(states.ndim, 2)
        self.assertEqual(actions.ndim, 2)
        self.assertEqual(actions.shape[1], 12)

    def test_nav_stitch_plans(self):
        backend = open_dataset_backend(RC365_ROOT)
        plans = build_nav_stitch_plans(backend, stitch_length=3, max_plans=5, seed=42)
        self.assertGreater(len(plans), 0)
        plan = plans[0]
        self.assertEqual(len(plan.segments), 3)
        fixtures = [s.target_fixture for s in plan.segments]
        self.assertEqual(len(set(fixtures)), 3)


if __name__ == "__main__":
    unittest.main()
