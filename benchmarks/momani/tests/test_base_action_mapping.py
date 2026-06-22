import unittest
import sys
from pathlib import Path

import numpy as np

NAVGEN_ROOT = Path(__file__).resolve().parents[1]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from controllers.closed_loop_navigator import map_base_action_for_env


class TestBaseActionMapping(unittest.TestCase):
    def test_default_mapping_swaps_xy(self):
        logical = np.array([0.2, -0.3, 0.4], dtype=float)
        mapped = map_base_action_for_env(logical)
        expected = np.array([-0.3, 0.2, 0.4], dtype=float)
        np.testing.assert_allclose(mapped, expected, atol=1e-9)

    def test_custom_mapping_order_and_sign(self):
        logical = np.array([0.5, 0.25, -0.75], dtype=float)
        mapped = map_base_action_for_env(
            logical,
            order=(0, 2, 1),
            sign=(-1.0, 1.0, -1.0),
        )
        expected = np.array([-0.5, -0.75, -0.25], dtype=float)
        np.testing.assert_allclose(mapped, expected, atol=1e-9)


if __name__ == "__main__":
    unittest.main()
