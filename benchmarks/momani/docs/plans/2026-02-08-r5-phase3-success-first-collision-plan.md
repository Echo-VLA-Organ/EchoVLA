# R5 Phase-3 Success-first Collision Reduction Plan

## 目标

- 主目标：保持 `success_rate >= 0.80`
- 次目标：把 `collision_step_rate` 从 `0.384`（r5_g4_n90）进一步压到 `<= 0.25`

## 当前基线

- 参考配置：`r5_g4_n90`
  - `success_rate = 0.822`
  - `collision_step_rate = 0.384`
  - `traj_collision_rate = 0.722`

## 观察驱动的优化方向

基于 `r5_g4_n90_collision_audit.json`，高频碰撞主要集中在：

- 岛台底座/门板边缘（`island_*`）
- 洗碗机外壳（`dishwasher_*`）
- 灶台壳体（`stove_*`）
- 柜门把手与门边（`*_door_handle_*`, `*_door_trim_*`）

## Phase-3 实验矩阵（30 demos, seed 固定）

### Group A: 语义加权障碍膨胀（不改控制）

- A1: handle/trim geom inflation +0.10m
- A2: handle/trim geom inflation +0.15m
- A3: island/stove/dishwasher geom inflation +0.08m

### Group B: 碰撞反应（轻量）

- B1: 连续碰撞 2 步后，速度缩放 0.6 持续 8 步
- B2: 连续碰撞 2 步后，后退 3 步 + 重规划一次

### Group C: 组合策略

- C1: A2 + B1
- C2: A3 + B2

## 评估与筛选规则

对每组统一输出：

- `success_rate`
- `collision_step_rate`
- `traj_collision_rate`
- `avg_traj_len`
- `success_subset.step_collision_rate`

筛选顺序：

1. 先过滤 `success_rate < 0.80`
2. 在剩余组里按 `collision_step_rate` 升序
3. 若并列，选 `avg_traj_len` 更短者

## 扩展验证

- Top-2 运行 60 demos
- Top-1 运行 90 demos

通过条件：

- 60 demos: `success_rate >= 0.80` 且 `collision_step_rate <= 0.30`
- 90 demos: `success_rate >= 0.78` 且 `collision_step_rate <= 0.25`

## 产线策略（阶段性）

- 主训练集：使用 Top-1 原始输出（不硬门禁）
- 副本 clean 集：离线门禁（例如 `collision_step_rate <= 0.30`）用于对比训练
