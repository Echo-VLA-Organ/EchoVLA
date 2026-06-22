import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

NAVGEN_ROOT = Path(__file__).resolve().parents[1]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from controllers.mg_navigate_lite import MGNavigateKitchenLite


class _DummyBaseController:
    def __init__(self):
        self.input_max = np.array([1.0, 1.0, 1.0], dtype=float)


class _DummyCompositeController:
    def __init__(self):
        self._action_split_indexes = {
            "base": (7, 10),
            "right_gripper": (10, 11),
        }
        self._base = _DummyBaseController()

    def get_controller(self, name):
        if name != "base":
            raise KeyError(name)
        return self._base


class _DummyRobot:
    def __init__(self):
        self.composite_controller = _DummyCompositeController()


class _DummyEnv:
    def __init__(self):
        self.action_dim = 12
        self.control_freq = 20
        self.robots = [_DummyRobot()]


class TestMGNavigateKitchenLite(unittest.TestCase):
    def test_get_base_action_slice(self):
        env = _DummyEnv()
        mg = MGNavigateKitchenLite(env)
        self.assertEqual(mg._get_base_action_slice(), (7, 10))

    def test_compose_action_sets_base_and_gripper(self):
        env = _DummyEnv()
        mg = MGNavigateKitchenLite(env)
        full = mg.compose_action(np.array([0.1, -0.2, 0.3]), np.array([0.5]))

        self.assertEqual(full.shape[0], 12)
        self.assertTrue(np.allclose(full[7:10], np.array([0.1, -0.2, 0.3])))
        self.assertAlmostEqual(float(full[10]), 0.5)

    def test_compose_action_scalar_gripper_broadcast(self):
        env = _DummyEnv()
        mg = MGNavigateKitchenLite(env)
        full = mg.compose_action(np.array([0.0, 0.0, 0.0]), np.array([0.2]))
        self.assertAlmostEqual(float(full[10]), 0.2)

    @unittest.skipUnless(
        importlib.util.find_spec("robosuite") is not None,
        "robosuite not installed",
    )
    def test_batch_generate_uses_lite_interface_by_default(self):
        from scripts.phase_d.batch_generate import _try_build_mg_interface

        env = _DummyEnv()
        mg = _try_build_mg_interface(env=env, enabled=True)
        self.assertIsInstance(mg, MGNavigateKitchenLite)


if __name__ == "__main__":
    unittest.main()
