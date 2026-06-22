# Collision Reduction Evaluation (Phase D)

## 背景

当前生成策略在成功率较高时仍伴随高 mobile-base 接触率，需要把“成功率”与“碰撞率”双指标一起优化。

## 对比实验设置

- 数据规模：30 demos（相同 source schedule）
- 控制参数：`phase_b_tune_precision.yaml` + `phase_c_tune_a.yaml`
- 实验组：
  1. `geometric`（baseline）
  2. `obstacle_aware`（A* 网格避障 waypoint）
  3. `obstacle_aware + collision gate(0.30)`

## 结果摘要

| 配置 | success_rate | collision_step_rate | traj_collision_rate | avg_traj_len |
|---|---:|---:|---:|---:|
| baseline geometric | 0.867 | 0.536 | 0.967 | 238.8 |
| obstacle_aware | 0.833 | 0.331 | 0.633 | 155.6 |
| obstacle_aware + gate=0.30 | 0.600 | 0.336 | 0.633 | 155.2 |

## 结论

1. `obstacle_aware` 显著降低碰撞：
   - 步级碰撞率从 `53.6%` 降到 `33.1%`（约 38% 相对下降）
   - 轨迹级碰撞率从 `96.7%` 降到 `63.3%`
2. 但碰撞率仍远高于目标（<5%），说明当前障碍建模仍过粗。
3. 碰撞门禁（0.30）能有效拦截高碰撞样本，但会将成功率压到 `60%`，当前不适合直接用于主数据集。

## R5 继续迭代（Success-first）

- 已完成固定 seed 的 R5 扩展实验，详见：
  - `reports/phase_d/r5/r5_success_first_progress.md`
- 当前最优配置（`r5_g4_n90`）达到：
  - `success_rate = 0.822`
  - `collision_step_rate = 0.384`
  - `traj_collision_rate = 0.722`
- 说明：相对 geometric 对照已显著降碰撞，但仍未达到低碰撞目标，需要进入语义加权障碍与碰撞反应策略。

## 建议下一步

1. 继续保留 `obstacle_aware` 作为主策略（比 geometric 明显更好）。
2. 碰撞门禁先用于“筛选副本数据集”，不要直接替换主训练集。
3. 下一轮优先改进障碍建模：
   - 从 geom 圆形近似升级为 bbox/mesh 包络
   - 为高频碰撞对象（门把手/柜体边缘）增加局部膨胀
   - 在路径平滑阶段加入“最近障碍距离约束”

## 2026-02-10 进展补充

- 已在 `robocasa/.venv` 运行时完成 per-geometry 膨胀试验（30 demos）。
- 对照：`metrics/phase_d/r5/r5_g4_rcvenv_n30.json`（success=0.600, collision_step_rate=0.337）。
- 激进权重试验：`metrics/phase_d/r5/r5_g4_geomap_rcvenv_n30.json`（success=0.533, collision_step_rate=0.352），tradeoff 变差。
- 保守 top-2 试验：`metrics/phase_d/r5/r5_g4_geomap_top2c_rcvenv_n30.json`（success=0.700, collision_step_rate=0.308），在 n=30 有正向提升。
- 但扩展验证显示收益未泛化：
  - `n=60`：`r5_g4_rcvenv_n60`(0.733, 0.238) vs `r5_g4_geomap_top2c_rcvenv_n60`(0.700, 0.240)
  - `n=90`：`r5_g4_rcvenv_n90`(0.644, 0.259) vs `r5_g4_geomap_top2c_rcvenv_n90`(0.611, 0.274)
- 结论：当前几何体加权方案不稳定，暂不替换 baseline；下一轮转向 collision response 机制（slowdown/replan）的小步对照实验。

## 交付层策略（2026-02-10）

- 在生成层继续使用 baseline；在交付层引入“碰撞阈值 + 指定数量”筛选。
- 交付脚本：`scripts/phase_d/deliver_dataset.py`
- 仅支持阈值：`0 / 0.1 / 0.2`。
- 不足时策略：严格失败（不自动放宽阈值，不重复采样）。
- 交付使用说明：`docs/phase_d_delivery.md`
