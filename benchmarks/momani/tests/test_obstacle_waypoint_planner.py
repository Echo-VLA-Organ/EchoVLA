import sys
import unittest
from pathlib import Path

import numpy as np

NAVGEN_ROOT = Path(__file__).resolve().parents[1]
if str(NAVGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(NAVGEN_ROOT))

from controllers.obstacle_waypoint_planner import (
    plan_2d_path,
    semantic_extra_inflation_for_geom,
)


class TestObstacleWaypointPlanner(unittest.TestCase):
    def test_semantic_extra_inflation_for_geom_keywords(self):
        self.assertAlmostEqual(
            semantic_extra_inflation_for_geom(
                "stack_1_main_group_1_door_handle_handle",
                handle_extra=0.10,
                heavy_extra=0.08,
            ),
            0.10,
        )
        self.assertAlmostEqual(
            semantic_extra_inflation_for_geom(
                "dishwasher_island_group_g2",
                handle_extra=0.10,
                heavy_extra=0.08,
            ),
            0.08,
        )
        self.assertAlmostEqual(
            semantic_extra_inflation_for_geom(
                "island_stack_1_left_door_handle_trim",
                handle_extra=0.10,
                heavy_extra=0.08,
            ),
            0.10,
        )
        self.assertAlmostEqual(
            semantic_extra_inflation_for_geom(
                "counter_main_group", handle_extra=0.10, heavy_extra=0.08
            ),
            0.0,
        )

    def test_semantic_extra_inflation_map_override(self):
        extra = semantic_extra_inflation_for_geom(
            "stove_main_group_g6",
            handle_extra=0.05,
            heavy_extra=0.08,
            geom_extra_inflation_map={
                "stove_main_group_g6": 0.20,
                "dishwasher_island_group_g2": 0.15,
            },
        )
        self.assertAlmostEqual(extra, 0.20)

    def test_planner_detours_around_blocking_obstacle(self):
        start = np.array([0.0, 0.0], dtype=float)
        goal = np.array([2.0, 0.0], dtype=float)
        obstacles = [(np.array([1.0, 0.0], dtype=float), 0.35)]

        path = plan_2d_path(
            start_xy=start,
            goal_xy=goal,
            obstacles=obstacles,
            resolution=0.1,
            margin=0.6,
        )

        self.assertGreater(len(path), 0)
        ys = [float(p[1]) for p in path]
        self.assertTrue(any(abs(y) > 0.2 for y in ys))

    def test_planner_returns_straight_path_without_obstacle(self):
        start = np.array([0.0, 0.0], dtype=float)
        goal = np.array([1.0, 0.0], dtype=float)
        path = plan_2d_path(
            start_xy=start,
            goal_xy=goal,
            obstacles=[],
            resolution=0.1,
            margin=0.4,
        )
        self.assertGreater(len(path), 0)
        self.assertAlmostEqual(float(path[0][0]), 0.0, places=3)
        self.assertAlmostEqual(float(path[-1][0]), 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
