from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple


ContactPair = Tuple[str, str]


def _is_mobile_collision_pair(
    geom1: Optional[str],
    geom2: Optional[str],
    mobile_prefix: str,
) -> bool:
    if geom1 is None or geom2 is None:
        return False
    g1_mobile = mobile_prefix in geom1
    g2_mobile = mobile_prefix in geom2
    return bool(g1_mobile ^ g2_mobile)


def extract_mobile_contact_targets(
    contact_pairs: Sequence[ContactPair],
    mobile_prefix: str = "mobilebase0",
) -> List[str]:
    targets: List[str] = []
    for geom1, geom2 in contact_pairs:
        if not _is_mobile_collision_pair(geom1, geom2, mobile_prefix=mobile_prefix):
            continue
        g1_mobile = mobile_prefix in geom1
        targets.append(geom2 if g1_mobile else geom1)
    return targets


def count_mobile_contacts(
    contact_pairs: Sequence[ContactPair],
    mobile_prefix: str = "mobilebase0",
) -> int:
    return int(
        len(extract_mobile_contact_targets(contact_pairs, mobile_prefix=mobile_prefix))
    )


def count_mobile_contacts_from_pairs(
    contact_pairs: Sequence[ContactPair],
    mobile_prefix: str = "mobilebase0",
) -> Dict:
    targets = extract_mobile_contact_targets(contact_pairs, mobile_prefix=mobile_prefix)
    counter = Counter(targets)
    return {
        "total_contacts": int(len(targets)),
        "unique_target_geoms": int(len(counter)),
        "target_counter": dict(counter),
    }


def collect_contact_pairs_from_sim(sim) -> List[ContactPair]:
    pairs: List[ContactPair] = []
    for i in range(sim.data.ncon):
        c = sim.data.contact[i]
        geom1 = sim.model.geom_id2name(int(c.geom1))
        geom2 = sim.model.geom_id2name(int(c.geom2))
        if geom1 is None or geom2 is None:
            continue
        pairs.append((str(geom1), str(geom2)))
    return pairs


def count_mobile_contacts_from_sim(sim, mobile_prefix: str = "mobilebase0") -> Dict:
    pairs = collect_contact_pairs_from_sim(sim)
    out = count_mobile_contacts_from_pairs(pairs, mobile_prefix=mobile_prefix)
    out["pairs"] = pairs
    return out


def apply_collision_gate(
    generated_traj_len: int,
    collision_steps: int,
    success: bool,
    current_stop_reason: str,
    collision_step_rate_limit: float,
) -> Dict[str, object]:
    rate = float(collision_steps / max(int(generated_traj_len), 1))
    if rate > float(collision_step_rate_limit):
        return {
            "success": False,
            "stop_reason": "collision_gate",
            "collision_step_rate": rate,
        }
    return {
        "success": bool(success),
        "stop_reason": str(current_stop_reason),
        "collision_step_rate": rate,
    }


def should_trigger_collision_response(
    consecutive_collision_steps: int,
    trigger_steps: int,
    triggers_used: int,
    max_triggers: int,
) -> bool:
    if max_triggers <= 0:
        return False
    if triggers_used >= max_triggers:
        return False
    if trigger_steps <= 0:
        return False
    return int(consecutive_collision_steps) >= int(trigger_steps)
