# R5 试验进展（Success-first）

## 目标与策略

- 目标：先把 `success_rate` 稳定在 `>= 0.80`，再持续降低碰撞率。
- 固定设置：`n=30`、`seed=20260208`、相同 source pool。
- 基线对照：
  - `r5_geometric_ref`（直线几何 waypoint）
  - `r5_base`（obstacle-aware baseline, inflation=0.18, margin=0.8, grid=0.10）

## Phase-1 参数矩阵结果（30 demos）

| run | success_rate | collision_step_rate | traj_collision_rate | avg_traj_len |
|---|---:|---:|---:|---:|
| r5_base | 0.733 | 0.463 | 0.767 | 164.1 |
| r5_g1 | 0.733 | 0.465 | 0.767 | 164.4 |
| r5_g2 | 0.767 | 0.443 | 0.767 | 158.0 |
| r5_g3 | 0.767 | 0.448 | 0.767 | 158.7 |
| **r5_g4** | **0.800** | **0.410** | 0.767 | **153.0** |
| r5_g5 | 0.733 | 0.462 | 0.767 | 163.4 |
| r5_g6 | 0.767 | 0.438 | 0.767 | 159.0 |
| r5_g7 | 0.733 | 0.497 | 0.767 | 174.7 |
| **r5_g8** | **0.800** | 0.431 | 0.767 | 161.1 |
| r5_g9 | 0.733 | 0.489 | 0.767 | 174.2 |

Top-2（按 success>=0.8 后 collision_step_rate 排序）：`r5_g4`, `r5_g8`

## Phase-2 扩展验证

| run | n | success_rate | collision_step_rate | traj_collision_rate | avg_traj_len |
|---|---:|---:|---:|---:|---:|
| r5_g4_n60 | 60 | 0.800 | 0.394 | 0.733 | 150.8 |
| r5_g8_n60 | 60 | 0.783 | 0.432 | 0.733 | 162.8 |
| r5_g4_n90 | 90 | **0.822** | **0.384** | **0.722** | **150.0** |

## 对照结论

- 与 `r5_geometric_ref` 相比：
  - success: `0.867 -> 0.822`（下降 4.5 个百分点）
  - collision_step_rate: `0.549 -> 0.384`（下降约 30%）
  - traj_collision_rate: `1.000 -> 0.722`（下降约 28%）
- 与旧 obstacle-aware 结果相比，R5 的 g4 在 success 上更稳，但碰撞率仍明显高（距离 <0.20 目标有差距）。

## 关键风险

- 高碰撞仍集中在固定类别几何体（门把手、柜体边缘、岛台/灶台/洗碗机壳体），见：
  - `metrics/phase_d/r5/r5_g4_n90_collision_audit.json`
- `success_subset` 仍有非低碰撞样本：`step_collision_rate = 0.1869`，说明“成功不代表干净轨迹”。

## 2026-02-10 运行时回切与几何体加权试验

- 运行时回切到：`/Users/candlest/dev/robocasa/.venv/bin/python`
- 先做基线 sanity（`n=10`）：
  - `metrics/phase_d/r5/r5_g4_rcvenv_sanity_n10.json`
  - `success_rate=0.700`, `collision_step_rate=0.292`
- 再做同配置基线（`n=30`）：
  - `metrics/phase_d/r5/r5_g4_rcvenv_n30.json`
  - `success_rate=0.600`, `collision_step_rate=0.337`, `traj_collision_rate=0.800`
- 进行 per-geometry 加权膨胀（`n=30`）：
  - 映射文件：`config/tuning/r5_geom_extra_inflation_top.json`
  - 结果：`metrics/phase_d/r5/r5_g4_geomap_rcvenv_n30.json`
  - `success_rate=0.533`, `collision_step_rate=0.352`, `traj_collision_rate=0.800`
- 结论：当前这版几何体加权膨胀未改善 tradeoff（相对同运行时基线 success 下降 6.7pp，碰撞率上升 1.5pp），不进入 60/90 扩展。
- 保守版 top-2 几何体加权（`n=30`）：
  - 映射文件：`config/tuning/r5_geom_extra_inflation_top2_conservative.json`
  - 结果：`metrics/phase_d/r5/r5_g4_geomap_top2c_rcvenv_n30.json`
  - `success_rate=0.700`, `collision_step_rate=0.308`, `traj_collision_rate=0.800`
  - 相对同运行时基线（`r5_g4_rcvenv_n30`）：success `+10.0pp`，collision_step_rate `-2.9pp`
- 补齐扩展对照（同运行时，同 seed/schedule）：
  - `metrics/phase_d/r5/r5_g4_rcvenv_n60.json` vs `metrics/phase_d/r5/r5_g4_geomap_top2c_rcvenv_n60.json`
  - `metrics/phase_d/r5/r5_g4_rcvenv_n90.json` vs `metrics/phase_d/r5/r5_g4_geomap_top2c_rcvenv_n90.json`
  - `n=60`: baseline `(0.733, 0.238)` vs top2c `(0.700, 0.240)`
  - `n=90`: baseline `(0.644, 0.259)` vs top2c `(0.611, 0.274)`
- 结论更新：top2c 在 `n=30` 的收益未能泛化到 `n=60/90`，不建议作为生产候选替代 baseline。
- 下一步建议：保持 baseline，下一轮改为“轻量 collision response（slowdown/replan）+ 不改几何体膨胀”再做 30-demo 对照。

## 交付方案更新

- 生成仍以 baseline 为主；交付改为离线筛选。
- 脚本：`scripts/phase_d/deliver_dataset.py`
- 口径：支持 `traj_collision_threshold in {0, 0.1, 0.2}` + `target_count`。
- 样本不足时严格失败，并给出 `recommended_raw_count`。
- 说明文档：`docs/phase_d_delivery.md`
