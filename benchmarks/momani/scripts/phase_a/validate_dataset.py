#!/usr/bin/env python3

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import h5py


NAVGEN_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATASET = str(NAVGEN_ROOT / "datasets/official/NavigateKitchen/demo.hdf5")
DEFAULT_OUTPUT = str(NAVGEN_ROOT / "metrics/phase_a/dataset_validation.json")


def _demo_sort_key(name: str):
    if name.startswith("demo_"):
        suffix = name.split("demo_", 1)[1]
        if suffix.isdigit():
            return (0, int(suffix))
    return (1, name)


def _safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def validate_dataset(
    dataset_path: str,
    expect_action_dim: int,
    expect_state_dim: int,
    base_start: int,
    base_end: int,
    base_mode_index: int,
):
    p = Path(dataset_path)
    if not p.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    issues = []
    lengths = []
    state_dims = Counter()
    action_dims = Counter()
    layout_counter = Counter()
    style_counter = Counter()
    fixture_pair_counter = Counter()
    base_mode_counter = Counter()

    global_action_min = math.inf
    global_action_max = -math.inf
    global_base_min = math.inf
    global_base_max = -math.inf

    with h5py.File(dataset_path, "r") as f:
        top_keys = list(f.keys())
        has_data = "data" in f
        has_mask = "mask" in f
        if not has_data:
            raise ValueError("Invalid dataset: missing top-level group 'data'")

        demo_names = sorted(list(f["data"].keys()), key=_demo_sort_key)

        for demo_name in demo_names:
            grp = f["data"][demo_name]
            if "states" not in grp or "actions" not in grp:
                issues.append({"demo": demo_name, "issue": "missing_states_or_actions"})
                continue

            states = grp["states"]
            actions = grp["actions"]

            if len(states.shape) != 2 or len(actions.shape) != 2:
                issues.append(
                    {
                        "demo": demo_name,
                        "issue": "states_or_actions_not_2d",
                        "states_shape": list(states.shape),
                        "actions_shape": list(actions.shape),
                    }
                )
                continue

            t_states, d_states = int(states.shape[0]), int(states.shape[1])
            t_actions, d_actions = int(actions.shape[0]), int(actions.shape[1])
            lengths.append(t_states)
            state_dims[d_states] += 1
            action_dims[d_actions] += 1

            if t_states != t_actions:
                issues.append(
                    {
                        "demo": demo_name,
                        "issue": "time_dim_mismatch",
                        "states_t": t_states,
                        "actions_t": t_actions,
                    }
                )

            if expect_state_dim > 0 and d_states != expect_state_dim:
                issues.append(
                    {
                        "demo": demo_name,
                        "issue": "unexpected_state_dim",
                        "expected": expect_state_dim,
                        "actual": d_states,
                    }
                )

            if d_actions != expect_action_dim:
                issues.append(
                    {
                        "demo": demo_name,
                        "issue": "unexpected_action_dim",
                        "expected": expect_action_dim,
                        "actual": d_actions,
                    }
                )

            arr = actions[:]
            local_min = float(arr.min())
            local_max = float(arr.max())
            global_action_min = min(global_action_min, local_min)
            global_action_max = max(global_action_max, local_max)

            if d_actions > base_end:
                base_arr = arr[:, base_start:base_end]
                global_base_min = min(global_base_min, float(base_arr.min()))
                global_base_max = max(global_base_max, float(base_arr.max()))

            if base_mode_index < d_actions:
                base_mode_vals = arr[:, base_mode_index]
                for v in base_mode_vals:
                    fv = _safe_float(v)
                    if fv is None:
                        continue
                    key = f"{fv:.3f}"
                    base_mode_counter[key] += 1

            ep_meta_raw = grp.attrs.get("ep_meta", None)
            if ep_meta_raw is not None:
                try:
                    ep_meta = json.loads(ep_meta_raw)
                    layout_counter[str(ep_meta.get("layout_id", "None"))] += 1
                    style_counter[str(ep_meta.get("style_id", "None"))] += 1
                    fixture_refs = ep_meta.get("fixture_refs", {})
                    src = str(fixture_refs.get("src_fixture", "None"))
                    tgt = str(fixture_refs.get("target_fixture", "None"))
                    fixture_pair_counter[f"{src} -> {tgt}"] += 1
                except Exception:
                    issues.append({"demo": demo_name, "issue": "invalid_ep_meta_json"})
            else:
                issues.append({"demo": demo_name, "issue": "missing_ep_meta"})

    num_demos = len(lengths)
    len_min = min(lengths) if lengths else None
    len_max = max(lengths) if lengths else None
    len_mean = (sum(lengths) / len(lengths)) if lengths else None
    len_median = sorted(lengths)[len(lengths) // 2] if lengths else None

    non_binary_base_mode = {}
    for k, c in base_mode_counter.items():
        if k not in {"-1.000", "1.000"}:
            non_binary_base_mode[k] = c

    return {
        "dataset_path": dataset_path,
        "summary": {
            "num_demos": num_demos,
            "traj_len": {
                "min": len_min,
                "max": len_max,
                "mean": len_mean,
                "median": len_median,
            },
            "top_keys": sorted(top_keys),
            "has_data_group": has_data,
            "has_mask_group": has_mask,
            "state_dims": dict(state_dims),
            "action_dims": dict(action_dims),
            "action_range": {
                "min": None if global_action_min is math.inf else global_action_min,
                "max": None if global_action_max is -math.inf else global_action_max,
            },
            "base_action_range": {
                "min": None if global_base_min is math.inf else global_base_min,
                "max": None if global_base_max is -math.inf else global_base_max,
            },
            "base_mode_values": dict(base_mode_counter),
            "non_binary_base_mode_values": non_binary_base_mode,
        },
        "distribution": {
            "layout_id": dict(layout_counter),
            "style_id": dict(style_counter),
            "fixture_pairs_top20": dict(fixture_pair_counter.most_common(20)),
        },
        "expectation": {
            "expect_action_dim": expect_action_dim,
            "expect_state_dim": expect_state_dim,
            "base_action_slice": [base_start, base_end],
            "base_mode_index": base_mode_index,
        },
        "issues": issues,
        "pass": len(issues) == 0,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Validate RoboCasa NavigateKitchen dataset"
    )
    parser.add_argument(
        "--dataset", default=DEFAULT_DATASET, help="Path to source demo.hdf5"
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to output json")
    parser.add_argument("--expect-action-dim", type=int, default=12)
    parser.add_argument(
        "--expect-state-dim",
        type=int,
        default=-1,
        help="Expected state dim. Set <=0 to allow mixed state dims.",
    )
    parser.add_argument("--base-start", type=int, default=7)
    parser.add_argument("--base-end", type=int, default=10)
    parser.add_argument("--base-mode-index", type=int, default=11)
    args = parser.parse_args()

    result = validate_dataset(
        dataset_path=args.dataset,
        expect_action_dim=args.expect_action_dim,
        expect_state_dim=args.expect_state_dim,
        base_start=args.base_start,
        base_end=args.base_end,
        base_mode_index=args.base_mode_index,
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")

    print(f"[validate_dataset] saved: {out}")
    print(f"[validate_dataset] demos: {result['summary']['num_demos']}")
    print(f"[validate_dataset] pass: {result['pass']}")
    print(f"[validate_dataset] issues: {len(result['issues'])}")


if __name__ == "__main__":
    main()
