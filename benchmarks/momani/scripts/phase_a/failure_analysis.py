#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


NAVGEN_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT = str(NAVGEN_ROOT / "metrics/phase_a/baseline_openloop_10.json")
DEFAULT_JSON_OUT = str(NAVGEN_ROOT / "metrics/phase_a/failure_analysis_10.json")
DEFAULT_MD_OUT = str(NAVGEN_ROOT / "reports/phase_a/failure_analysis_10.md")


def classify_failure(
    item, pos_success_th, yaw_success_deg, early_step_th, severe_pos_err_th
):
    traj_len = int(item.get("traj_len", 0))
    div_step = item.get("divergence_step", None)
    pos_err = float(item.get("final_pos_error", 1e9))
    yaw_err = float(item.get("final_yaw_error_deg", 1e9))
    max_state_error = float(item.get("max_state_error", 0.0))

    if item.get("success", False):
        return "success", "已满足任务成功判定"

    if (
        div_step is not None
        and div_step <= early_step_th
        and max_state_error >= severe_pos_err_th
    ):
        return "early_heading_bias", "早期即发生明显偏离（开环首段失配）"

    if pos_err <= max(0.5, 2.0 * pos_success_th) and yaw_err > yaw_success_deg:
        return "late_alignment_failure", "末段靠近目标但朝向未对齐"

    if pos_err > pos_success_th:
        if div_step is not None and traj_len > 0 and div_step < int(0.6 * traj_len):
            return "mid_drift", "中段漂移导致末端位置误差较大"
        return "mid_drift", "位置误差未收敛，表现为路径漂移"

    return "late_alignment_failure", "位置接近但角度误差仍超阈值"


def build_report(data, rules):
    results = data.get("results", [])
    categorized = {
        "success": [],
        "early_heading_bias": [],
        "mid_drift": [],
        "late_alignment_failure": [],
    }

    for item in results:
        label, reason = classify_failure(
            item,
            pos_success_th=rules["pos_success_th"],
            yaw_success_deg=rules["yaw_success_deg"],
            early_step_th=rules["early_step_th"],
            severe_pos_err_th=rules["severe_pos_err_th"],
        )
        row = dict(item)
        row["failure_type"] = label
        row["failure_reason"] = reason
        categorized[label].append(row)

    failures = [r for r in results if not r.get("success", False)]
    failure_count = len(failures)

    type_counts = {
        "early_heading_bias": len(categorized["early_heading_bias"]),
        "mid_drift": len(categorized["mid_drift"]),
        "late_alignment_failure": len(categorized["late_alignment_failure"]),
    }

    def pick_examples(rows, k=2):
        return [
            {
                "demo_id": r.get("demo_id"),
                "traj_len": r.get("traj_len"),
                "divergence_step": r.get("divergence_step"),
                "max_state_error": r.get("max_state_error"),
                "final_pos_error": r.get("final_pos_error"),
                "final_yaw_error_deg": r.get("final_yaw_error_deg"),
                "layout_id": r.get("layout_id"),
                "style_id": r.get("style_id"),
                "lang": r.get("lang"),
            }
            for r in rows[:k]
        ]

    examples = {
        "early_heading_bias": pick_examples(categorized["early_heading_bias"], 3),
        "mid_drift": pick_examples(categorized["mid_drift"], 3),
        "late_alignment_failure": pick_examples(
            categorized["late_alignment_failure"], 3
        ),
    }

    return {
        "input_file": data.get("dataset_path"),
        "n_trials": len(results),
        "success_count": len(categorized["success"]),
        "failure_count": failure_count,
        "failure_type_counts": type_counts,
        "rules": rules,
        "examples": examples,
        "annotated_results": [
            row
            for key in [
                "success",
                "early_heading_bias",
                "mid_drift",
                "late_alignment_failure",
            ]
            for row in categorized[key]
        ],
    }


def render_markdown(report):
    n = report["n_trials"]
    succ = report["success_count"]
    fail = report["failure_count"]
    counts = report["failure_type_counts"]
    rules = report["rules"]

    lines = []
    lines.append("# NavigateKitchen 开环失败归因报告 (10 demos)")
    lines.append("")
    lines.append("## 总览")
    lines.append(f"- 样本数: {n}")
    lines.append(f"- 成功数: {succ}")
    lines.append(f"- 失败数: {fail}")
    lines.append("- 失败类型统计:")
    lines.append(f"  - early_heading_bias: {counts['early_heading_bias']}")
    lines.append(f"  - mid_drift: {counts['mid_drift']}")
    lines.append(f"  - late_alignment_failure: {counts['late_alignment_failure']}")
    lines.append("")
    lines.append("## 分类规则")
    lines.append(f"- pos_success_th: {rules['pos_success_th']} m")
    lines.append(f"- yaw_success_deg: {rules['yaw_success_deg']} deg")
    lines.append(f"- early_step_th: {rules['early_step_th']} steps")
    lines.append(f"- severe_pos_err_th: {rules['severe_pos_err_th']}")
    lines.append("")

    for key, title in [
        ("early_heading_bias", "早期偏航"),
        ("mid_drift", "中段漂移"),
        ("late_alignment_failure", "末段对齐失败"),
    ]:
        lines.append(f"## {title}")
        rows = report["examples"].get(key, [])
        if not rows:
            lines.append("- 无样例")
            lines.append("")
            continue
        for r in rows:
            lines.append(
                "- "
                f"{r['demo_id']}: div_step={r['divergence_step']}, "
                f"max_state_err={r['max_state_error']:.3f}, "
                f"pos_err={r['final_pos_error']:.3f}, "
                f"yaw_err_deg={r['final_yaw_error_deg']:.2f}, "
                f"layout={r['layout_id']}, style={r['style_id']}, "
                f"lang={r['lang']}"
            )
        lines.append("")

    lines.append("## 结论")
    lines.append("- 当前开环回放在首段就出现状态偏离，闭环控制为必要路径。")
    lines.append("- 下一步建议直接进入 Phase B：子目标闭环控制与场景固定管道。")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Failure analysis for open-loop baseline"
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, help="baseline_openloop json")
    parser.add_argument(
        "--json-output", default=DEFAULT_JSON_OUT, help="analysis json output"
    )
    parser.add_argument(
        "--md-output", default=DEFAULT_MD_OUT, help="analysis markdown output"
    )
    parser.add_argument("--pos-success-th", type=float, default=0.20)
    parser.add_argument("--yaw-success-deg", type=float, default=11.5)
    parser.add_argument("--early-step-th", type=int, default=5)
    parser.add_argument("--severe-pos-err-th", type=float, default=2.5)
    args = parser.parse_args()

    in_path = Path(args.input)
    data = json.loads(in_path.read_text(encoding="utf-8"))
    rules = {
        "pos_success_th": args.pos_success_th,
        "yaw_success_deg": args.yaw_success_deg,
        "early_step_th": args.early_step_th,
        "severe_pos_err_th": args.severe_pos_err_th,
    }

    report = build_report(data, rules)
    md = render_markdown(report)

    out_json = Path(args.json_output)
    out_md = Path(args.md_output)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(
        json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    out_md.write_text(md, encoding="utf-8")

    print(f"[failure_analysis] json: {out_json}")
    print(f"[failure_analysis] md: {out_md}")
    print(
        f"[failure_analysis] counts: {json.dumps(report['failure_type_counts'], ensure_ascii=True)}"
    )


if __name__ == "__main__":
    main()
