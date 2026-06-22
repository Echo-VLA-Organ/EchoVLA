#!/usr/bin/env python3

import argparse
import glob
import json
from collections import Counter
from pathlib import Path
from statistics import mean


NAVGEN_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT_GLOB = str(NAVGEN_ROOT / "metrics/phase_b/closed_loop_eval_10_s*.json")
DEFAULT_JSON_OUT = str(NAVGEN_ROOT / "metrics/phase_b/failure_analysis_multi.json")
DEFAULT_MD_OUT = str(NAVGEN_ROOT / "reports/phase_b/failure_analysis_multi.md")


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _classify_result(r, pos_th=0.20, yaw_th=11.5):
    pos_ok = float(r.get("final_pos_error", 1e9)) <= pos_th
    yaw_ok = float(r.get("final_yaw_error_deg", 1e9)) <= yaw_th

    if r.get("success", False):
        return "success"
    if (not pos_ok) and yaw_ok:
        return "pos_not_converged"
    if pos_ok and (not yaw_ok):
        return "yaw_not_converged"
    return "pos_and_yaw_not_converged"


def _recommendations(stats):
    recs = []
    if stats["success_rate"] == 0.0:
        recs.append("先降低任务难度：仅测试前 5 个 waypoint，确认单段闭环能稳定收敛")

    if stats["max_steps_hit_rate"] >= 0.75:
        recs.append(
            "减少 waypoint 数量：将 step_interval 从 10 提到 20，优先验证终点收敛"
        )
        recs.append("提升每步推进能力：smoothing.alpha 从 0.30 降到 0.15，减小动作迟滞")

    if stats["avg_timeout_waypoints"] >= 6.0:
        recs.append("放宽 waypoint 到达阈值：reached_threshold_m 从 0.15 放宽到 0.22")
        recs.append("暂时降低门控保守性：ori_priority_threshold_deg 从 17 提到 25")

    major = stats["failure_type_counts"]
    if major.get("pos_not_converged", 0) + major.get(
        "pos_and_yaw_not_converged", 0
    ) >= max(1, int(stats["n_trials"] * 0.7)):
        recs.append(
            "位置收敛是主瓶颈：先加大平移推进（vx_max 0.8->1.0, vy_max 0.6->0.8）"
        )
        recs.append("减速触发更晚：deceleration.distance_threshold_m 从 0.50 降到 0.25")

    if not recs:
        recs.append("先做 20 条 A/B：只改 step_interval 与 smoothing.alpha 两个参数")
    return recs


def _to_markdown(report):
    s = report["summary"]
    lines = []
    lines.append("# Phase B 多批次失败分析")
    lines.append("")
    lines.append("## 总体结果")
    lines.append(f"- 批次数: {s['n_runs']}")
    lines.append(f"- 样本数: {s['n_trials']}")
    lines.append(f"- 成功率: {s['success_rate']:.3f}")
    lines.append(f"- 命中 max_steps 比例: {s['max_steps_hit_rate']:.3f}")
    lines.append(f"- 平均终点位置误差: {s['avg_final_pos_error']:.3f} m")
    lines.append(f"- 平均终点朝向误差: {s['avg_final_yaw_error_deg']:.2f} deg")
    lines.append(f"- 平均 waypoint 到达数: {s['avg_reached_waypoints']:.2f}")
    lines.append(f"- 平均 waypoint 超时数: {s['avg_timeout_waypoints']:.2f}")
    lines.append("")
    lines.append("## 失败类型")
    for k, v in s["failure_type_counts"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## 每批次摘要")
    for run in report["runs"]:
        rs = run["summary"]
        lines.append(
            f"- {run['file']}: success_rate={rs['success_rate']:.3f}, "
            f"avg_pos_err={rs['avg_final_pos_error']:.3f}, avg_yaw_err={rs['avg_final_yaw_error_deg']:.2f}, "
            f"avg_gen_len={rs['avg_generated_traj_len']:.1f}"
        )
    lines.append("")
    lines.append("## 首轮调参建议")
    for i, rec in enumerate(report["recommendations"], start=1):
        lines.append(f"{i}. {rec}")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze multiple Phase B runs")
    parser.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB)
    parser.add_argument("--json-output", default=DEFAULT_JSON_OUT)
    parser.add_argument("--md-output", default=DEFAULT_MD_OUT)
    parser.add_argument("--pos-th", type=float, default=0.20)
    parser.add_argument("--yaw-th", type=float, default=11.5)
    args = parser.parse_args()

    files = [Path(p) for p in sorted(glob.glob(args.input_glob))]
    if not files:
        raise FileNotFoundError(f"no files matched: {args.input_glob}")

    runs = []
    all_results = []
    max_steps = None

    for fp in files:
        data = _load_json(fp)
        runs.append({"file": str(fp), "summary": data.get("summary", {})})
        all_results.extend(data.get("results", []))
        if max_steps is None:
            max_steps = int(data.get("config", {}).get("max_steps_per_demo", 500))

    if max_steps is None:
        max_steps = 500

    n = len(all_results)
    success_count = sum(1 for r in all_results if r.get("success", False))
    max_steps_hit = sum(
        1
        for r in all_results
        if int(r.get("generated_traj_len", 0)) >= int(max_steps * 0.98)
    )

    failure_type_counts = Counter()
    for r in all_results:
        failure_type_counts[_classify_result(r, args.pos_th, args.yaw_th)] += 1

    summary = {
        "n_runs": len(runs),
        "n_trials": n,
        "success_count": success_count,
        "success_rate": (success_count / n) if n else 0.0,
        "max_steps_hit_rate": (max_steps_hit / n) if n else 0.0,
        "avg_final_pos_error": mean(
            float(r.get("final_pos_error", 0.0)) for r in all_results
        ),
        "avg_final_yaw_error_deg": mean(
            float(r.get("final_yaw_error_deg", 0.0)) for r in all_results
        ),
        "avg_generated_traj_len": mean(
            float(r.get("generated_traj_len", 0.0)) for r in all_results
        ),
        "avg_reached_waypoints": mean(
            float(r.get("reached_waypoints", 0.0)) for r in all_results
        ),
        "avg_timeout_waypoints": mean(
            float(r.get("timeout_waypoints", 0.0)) for r in all_results
        ),
        "failure_type_counts": dict(failure_type_counts),
    }

    report = {
        "input_files": [str(x) for x in files],
        "summary": summary,
        "runs": runs,
        "recommendations": _recommendations(summary),
    }

    out_json = Path(args.json_output)
    out_md = Path(args.md_output)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(
        json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    out_md.write_text(_to_markdown(report), encoding="utf-8")

    print(f"[analyze_failures] json: {out_json}")
    print(f"[analyze_failures] md: {out_md}")
    print(f"[analyze_failures] summary: {json.dumps(summary, ensure_ascii=True)}")


if __name__ == "__main__":
    main()
