# Phase D 执行结果

## 交付物

- 生成数据集：`datasets/navgen/v1/demo.hdf5`
- 生成汇总：`metrics/phase_d/generation_summary.json`
- 失败样本：`metrics/phase_d/failure_cases.jsonl`
- 训练校验：
  - `metrics/phase_d/training_validation.json`
  - `reports/phase_d/training_validation.md`

## 最终指标（100 demos）

- `success_rate`: **0.84** (84 / 100)
- `avg_final_pos_error`: 0.373 m
- `avg_final_yaw_error_deg`: 3.02
- `avg_traj_len`: 232.86
- `stop_reason`: success 84 / waypoint_timeout 12 / max_steps 4

## 数据完整性

- `empty_traj_count`: 0
- `nan_count`: 0
- `inf_count`: 0
- `action_oob_count`: 0
- `action_range`: [-1.0, 1.0]
- 训练校验 `pass: true`

## 新增风险：碰撞率审计（mobile base 接触）

- 审计口径：统计 `mobilebase0_*` 与非 mobile-base 几何体的接触（MuJoCo contact）。
- 生成数据（本次 100 条）：
  - 轨迹级碰撞率：`98%`（98 / 100）
  - 步级碰撞率：`55.26%`（12868 / 23286）
- 官方数据（NavigateKitchen 90 条）对比：
  - 轨迹级碰撞率：`24.44%`（22 / 90）
  - 步级碰撞率：`0.95%`（147 / 15500）
- 按成功/失败分组（生成数据）：
  - 成功轨迹步级碰撞率：`45.09%`
  - 失败轨迹步级碰撞率：`80.36%`

结论：当前成功率已达标，但碰撞行为显著高于官方分布，存在训练偏差与部署安全风险。下一步需将碰撞指标纳入硬门禁并改造路径策略。

## 碰撞治理阶段进展（Round-1）

- 已新增：
  - 碰撞审计脚本：`scripts/phase_d/collision_audit.py`
  - 碰撞统计工具：`utils/collision_metrics.py`
  - 碰撞门禁能力（可配置阈值）：`scripts/phase_d/batch_generate.py`
  - obstacle-aware waypoint 规划：`controllers/obstacle_waypoint_planner.py`
- 30条对比结果见：`reports/phase_d/collision_reduction_eval.md`
  - `geometric -> obstacle_aware`：碰撞率明显下降，但仍高于目标阈值

## 失败热点（建议优先排查）

- `demo_25`, `demo_44`, `demo_50`, `demo_3`, `demo_19`（高位置误差或 max_steps）
- `demo_34`（朝向误差偏大）

## 结论

Phase D 已完成，且核心 KPI（>=75% 成功率）达成。当前数据可用于下一步训练与策略迭代。
