import heapq
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


Obstacle2D = Tuple[np.ndarray, float]


def semantic_extra_inflation_for_geom(
    geom_name: str,
    handle_extra: float = 0.0,
    heavy_extra: float = 0.0,
    geom_extra_inflation_map: Optional[Dict[str, float]] = None,
) -> float:
    lname = str(geom_name).lower()
    extra = 0.0
    if ("handle" in lname) or ("trim" in lname):
        extra = max(extra, float(handle_extra))
    if ("island_" in lname) or ("stove_" in lname) or ("dishwasher_" in lname):
        extra = max(extra, float(heavy_extra))
    if geom_extra_inflation_map:
        mapped = geom_extra_inflation_map.get(str(geom_name), 0.0)
        extra = max(extra, float(mapped))
    return float(max(extra, 0.0))


def _estimate_geom_radius(geom_type: int, geom_size: np.ndarray) -> float:
    if geom_type == 2:  # sphere
        return float(max(geom_size[0], 0.02))
    if geom_type in (3, 5):  # capsule / cylinder
        return float(max(geom_size[0], 0.02))
    if geom_type == 6:  # box
        return float(max(np.linalg.norm(geom_size[:2]), 0.03))
    return float(max(geom_size[0], geom_size[1], 0.05))


def extract_scene_obstacles(
    env,
    inflation_m: float = 0.18,
    semantic_handle_extra_inflation: float = 0.0,
    semantic_heavy_extra_inflation: float = 0.0,
    geom_extra_inflation_map: Optional[Dict[str, float]] = None,
    mobile_prefix: str = "mobilebase0",
    ignore_name_keywords: Sequence[str] = ("floor", "wall", "ceiling", "skybox"),
) -> List[Obstacle2D]:
    sim = env.sim
    obstacles: List[Obstacle2D] = []

    for gid in range(sim.model.ngeom):
        name = sim.model.geom_id2name(gid)
        if name is None:
            continue
        name = str(name)
        lname = name.lower()
        if mobile_prefix in name:
            continue
        if any(k in lname for k in ignore_name_keywords):
            continue

        contype = int(sim.model.geom_contype[gid])
        conaff = int(sim.model.geom_conaffinity[gid])
        if contype == 0 and conaff == 0:
            continue

        gtype = int(sim.model.geom_type[gid])
        if gtype in (0, 1):  # plane / hfield
            continue

        center_xy = np.array(sim.data.geom_xpos[gid][:2], dtype=float)
        size = np.array(sim.model.geom_size[gid], dtype=float)
        semantic_extra = semantic_extra_inflation_for_geom(
            name,
            handle_extra=semantic_handle_extra_inflation,
            heavy_extra=semantic_heavy_extra_inflation,
            geom_extra_inflation_map=geom_extra_inflation_map,
        )
        radius = (
            _estimate_geom_radius(gtype, size) + float(inflation_m) + semantic_extra
        )
        obstacles.append((center_xy, radius))

    return obstacles


def _world_to_grid(
    point_xy: np.ndarray,
    min_xy: np.ndarray,
    resolution: float,
) -> Tuple[int, int]:
    gx = int(np.round((point_xy[0] - min_xy[0]) / resolution))
    gy = int(np.round((point_xy[1] - min_xy[1]) / resolution))
    return gx, gy


def _grid_to_world(
    grid_xy: Tuple[int, int],
    min_xy: np.ndarray,
    resolution: float,
) -> np.ndarray:
    return np.array(
        [
            min_xy[0] + grid_xy[0] * resolution,
            min_xy[1] + grid_xy[1] * resolution,
        ],
        dtype=float,
    )


def _reconstruct_path(came_from, current):
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def _a_star(
    occupancy: np.ndarray,
    start: Tuple[int, int],
    goal: Tuple[int, int],
) -> Optional[List[Tuple[int, int]]]:
    w, h = occupancy.shape[0], occupancy.shape[1]

    def in_bounds(n):
        return 0 <= n[0] < w and 0 <= n[1] < h

    neighbors = [
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
    ]

    open_heap = []
    heapq.heappush(open_heap, (0.0, start))
    came_from = {}
    g_score = {start: 0.0}

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current == goal:
            return _reconstruct_path(came_from, current)

        for dx, dy in neighbors:
            nxt = (current[0] + dx, current[1] + dy)
            if not in_bounds(nxt):
                continue
            if occupancy[nxt[0], nxt[1]]:
                continue
            cost = np.hypot(dx, dy)
            cand = g_score[current] + float(cost)
            if cand < g_score.get(nxt, np.inf):
                came_from[nxt] = current
                g_score[nxt] = cand
                h_score = float(np.hypot(goal[0] - nxt[0], goal[1] - nxt[1]))
                heapq.heappush(open_heap, (cand + h_score, nxt))

    return None


def plan_2d_path(
    start_xy: np.ndarray,
    goal_xy: np.ndarray,
    obstacles: Sequence[Obstacle2D],
    resolution: float = 0.10,
    margin: float = 0.8,
) -> List[np.ndarray]:
    start_xy = np.array(start_xy, dtype=float).reshape(2)
    goal_xy = np.array(goal_xy, dtype=float).reshape(2)
    res = float(max(resolution, 0.02))
    mg = float(max(margin, 0.2))

    points = [start_xy, goal_xy] + [
        np.array(c, dtype=float).reshape(2) for c, _ in obstacles
    ]
    min_xy = np.min(np.stack(points, axis=0), axis=0) - mg
    max_xy = np.max(np.stack(points, axis=0), axis=0) + mg

    width = int(np.ceil((max_xy[0] - min_xy[0]) / res)) + 1
    height = int(np.ceil((max_xy[1] - min_xy[1]) / res)) + 1
    width = max(width, 3)
    height = max(height, 3)

    occupancy = np.zeros((width, height), dtype=bool)
    for center, radius in obstacles:
        c = np.array(center, dtype=float).reshape(2)
        r = float(max(radius, 0.01))
        x0, y0 = _world_to_grid(c - r, min_xy=min_xy, resolution=res)
        x1, y1 = _world_to_grid(c + r, min_xy=min_xy, resolution=res)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, width - 1), min(y1, height - 1)
        for gx in range(x0, x1 + 1):
            for gy in range(y0, y1 + 1):
                p = _grid_to_world((gx, gy), min_xy=min_xy, resolution=res)
                if np.linalg.norm(p - c) <= r:
                    occupancy[gx, gy] = True

    start = _world_to_grid(start_xy, min_xy=min_xy, resolution=res)
    goal = _world_to_grid(goal_xy, min_xy=min_xy, resolution=res)
    start = (min(max(start[0], 0), width - 1), min(max(start[1], 0), height - 1))
    goal = (min(max(goal[0], 0), width - 1), min(max(goal[1], 0), height - 1))

    occupancy[start[0], start[1]] = False
    occupancy[goal[0], goal[1]] = False

    grid_path = _a_star(occupancy=occupancy, start=start, goal=goal)
    if grid_path is None:
        return [start_xy, goal_xy]

    world_path = [_grid_to_world(g, min_xy=min_xy, resolution=res) for g in grid_path]

    # light simplification: keep turning points and every Nth point
    simplified: List[np.ndarray] = []
    for i, p in enumerate(world_path):
        if i == 0 or i == len(world_path) - 1:
            simplified.append(p)
            continue
        if i % 3 == 0:
            simplified.append(p)
            continue
        prev = world_path[i - 1]
        nxt = world_path[i + 1]
        v1 = p - prev
        v2 = nxt - p
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 < 1e-8 or n2 < 1e-8:
            continue
        cosang = float(np.dot(v1, v2) / (n1 * n2))
        if cosang < 0.98:
            simplified.append(p)

    if np.linalg.norm(simplified[0] - start_xy) > 1e-6:
        simplified.insert(0, start_xy)
    if np.linalg.norm(simplified[-1] - goal_xy) > 1e-6:
        simplified.append(goal_xy)
    return simplified
