"""Multi-leg navigation stitching for MoMani (same kitchen, sequential targets)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from utils.dataset_backend import BaseDatasetBackend, DemoRecord


@dataclass
class NavStitchSegment:
    demo_id: str
    lang: str
    target_fixture: Optional[str]
    layout_id: Optional[int]
    style_id: Optional[int]


@dataclass
class NavStitchPlan:
    plan_id: str
    layout_id: Optional[int]
    style_id: Optional[int]
    segments: List[NavStitchSegment] = field(default_factory=list)


def apply_nav_segment_target(env, ep_meta: Dict[str, Any]) -> None:
    """Update NavigateKitchen target fixture without rebuilding the full scene."""
    if hasattr(env, "set_attrs_from_ep_meta"):
        env.set_attrs_from_ep_meta(ep_meta)
    elif hasattr(env, "set_ep_meta"):
        env.set_ep_meta(ep_meta)
    if hasattr(env, "update_sites"):
        env.update_sites()
    if hasattr(env, "update_state"):
        env.update_state()


def _layout_key(record: DemoRecord) -> str:
    return f"{record.layout_id}:{record.style_id}"


def group_records_by_layout(records: Sequence[DemoRecord]) -> Dict[str, List[DemoRecord]]:
    buckets: Dict[str, List[DemoRecord]] = {}
    for rec in records:
        if rec.layout_id is None or rec.style_id is None:
            continue
        buckets.setdefault(_layout_key(rec), []).append(rec)
    for key in buckets:
        buckets[key].sort(key=lambda r: r.episode_index)
    return buckets


def build_nav_stitch_plans(
    backend: BaseDatasetBackend,
    *,
    stitch_length: int = 3,
    max_plans: int = 10,
    seed: int = 42,
    require_unique_targets: bool = True,
) -> List[NavStitchPlan]:
    """Build multi-leg nav plans from episodes sharing layout/style."""
    if stitch_length < 2:
        raise ValueError("stitch_length must be >= 2")

    rng = np.random.default_rng(seed)
    records = backend.list_demo_records()
    grouped = group_records_by_layout(records)

    plans: List[NavStitchPlan] = []
    group_keys = sorted(grouped.keys())
    rng.shuffle(group_keys)

    for gkey in group_keys:
        pool = list(grouped[gkey])
        if len(pool) < stitch_length:
            continue

        used_targets: set[str] = set()
        segments: List[NavStitchSegment] = []
        for rec in pool:
            tgt = rec.target_fixture or rec.lang
            if require_unique_targets and tgt in used_targets:
                continue
            used_targets.add(tgt)
            segments.append(
                NavStitchSegment(
                    demo_id=rec.demo_id,
                    lang=rec.lang,
                    target_fixture=rec.target_fixture,
                    layout_id=rec.layout_id,
                    style_id=rec.style_id,
                )
            )
            if len(segments) >= stitch_length:
                break

        if len(segments) < stitch_length:
            continue

        layout_id, style_id = segments[0].layout_id, segments[0].style_id
        plan_id = f"stitch_{layout_id}_{style_id}_{len(plans):04d}"
        plans.append(
            NavStitchPlan(
                plan_id=plan_id,
                layout_id=layout_id,
                style_id=style_id,
                segments=segments,
            )
        )
        if len(plans) >= max_plans:
            break

    return plans


def plan_to_dict(plan: NavStitchPlan) -> Dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "layout_id": plan.layout_id,
        "style_id": plan.style_id,
        "segments": [
            {
                "demo_id": s.demo_id,
                "lang": s.lang,
                "target_fixture": s.target_fixture,
            }
            for s in plan.segments
        ],
    }
