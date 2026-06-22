import math
from typing import Any, Dict, List, Sequence, Tuple


ALLOWED_TRAJ_COLLISION_THRESHOLDS: Tuple[float, float, float] = (0.0, 0.1, 0.2)


def normalize_traj_collision_threshold(value: float) -> float:
    x = float(value)
    for allowed in ALLOWED_TRAJ_COLLISION_THRESHOLDS:
        if abs(x - allowed) < 1e-9:
            return float(allowed)
    opts = ", ".join(str(v) for v in ALLOWED_TRAJ_COLLISION_THRESHOLDS)
    raise ValueError(f"unsupported traj collision threshold: {value}, allowed: {opts}")


def _demo_sort_key(demo_id: str) -> Tuple[int, Any]:
    s = str(demo_id)
    if s.startswith("demo_"):
        suf = s.split("demo_", 1)[1]
        if suf.isdigit():
            return (0, int(suf))
    return (1, s)


def _record_rank_key(
    rec: Dict[str, Any],
) -> Tuple[float, float, float, Tuple[int, Any]]:
    has_collision = bool(rec.get("has_collision", False))
    collision_step_rate = float(rec.get("collision_step_rate", 0.0))
    final_pos_error = float(rec.get("final_pos_error", math.inf))
    return (
        1.0 if has_collision else 0.0,
        collision_step_rate,
        final_pos_error,
        _demo_sort_key(str(rec.get("demo_id", ""))),
    )


def select_delivery_subset(
    records: Sequence[Dict[str, Any]],
    target_count: int,
    traj_collision_threshold: float,
    success_only: bool = True,
) -> Dict[str, Any]:
    threshold = normalize_traj_collision_threshold(traj_collision_threshold)
    target = int(target_count)
    if target <= 0:
        raise ValueError("target_count must be > 0")

    eligible: List[Dict[str, Any]] = []
    for rec in records:
        if success_only and (not bool(rec.get("success", False))):
            continue
        eligible.append(dict(rec))

    eligible_sorted = sorted(eligible, key=_record_rank_key)
    non_collision = [
        r for r in eligible_sorted if not bool(r.get("has_collision", False))
    ]
    collision = [r for r in eligible_sorted if bool(r.get("has_collision", False))]

    if len(eligible_sorted) < target:
        raise ValueError(
            f"insufficient eligible samples: need={target}, have={len(eligible_sorted)}"
        )

    allowed_collision = int(math.floor(threshold * target + 1e-9))
    min_non_collision_needed = target - allowed_collision
    if len(non_collision) < min_non_collision_needed:
        raise ValueError(
            "insufficient non-collision samples for threshold: "
            f"need_non_collision>={min_non_collision_needed}, have_non_collision={len(non_collision)}, "
            f"threshold={threshold}, target={target}"
        )

    selected: List[Dict[str, Any]] = []
    if len(non_collision) >= target:
        selected = non_collision[:target]
    else:
        selected = list(non_collision)
        needed_collision = target - len(selected)
        selected.extend(collision[:needed_collision])

    selected_collision_count = sum(
        1 for r in selected if bool(r.get("has_collision", False))
    )
    selected_traj_collision_rate = float(selected_collision_count / max(target, 1))
    if selected_traj_collision_rate > threshold + 1e-9:
        raise ValueError(
            "internal selection error: selected traj collision rate exceeds threshold"
        )

    return {
        "threshold": threshold,
        "target_count": target,
        "success_only": bool(success_only),
        "eligible_count": int(len(eligible_sorted)),
        "available_non_collision_count": int(len(non_collision)),
        "available_collision_count": int(len(collision)),
        "allowed_collision_count": int(allowed_collision),
        "selected_collision_count": int(selected_collision_count),
        "selected_traj_collision_rate": float(selected_traj_collision_rate),
        "selected_records": selected,
    }
