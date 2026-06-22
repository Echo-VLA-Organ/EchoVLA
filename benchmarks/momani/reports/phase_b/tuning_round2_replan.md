# Phase B 调参 Round-2（Stuck Replan）

## 本轮改动

- 在 `test_closed_loop.py` 加入卡住检测与子目标重规划：
  - `--stuck-replan-enabled`
  - `--stuck-window`
  - `--stuck-min-progress-m`
  - `--stuck-replan-max-per-waypoint`
  - `--stuck-replan-ratio`
- step trace 新增调试字段：
  - `base_action_norm`
  - `delta_pos_error_per_10_steps`
  - `stuck_counter`
  - `replan_counter`

## 对比结果（10 demos, start=0）

| run | success_rate | avg_pos_err(m) | avg_yaw_err(deg) | avg_timeout_wp | avg_replan |
|---|---:|---:|---:|---:|---:|
| r2-noreplan | 0.00 | 2.892 | 12.33 | 7.4 | 0.0 |
| r2-replan(aggressive) | 0.00 | 2.998 | 11.30 | 7.3 | 13.6 |
| r2-replan(gentle) | 0.00 | 2.956 | 11.16 | 7.4 | 6.9 |

## 结论

1. 卡住检测可触发大量 replan，但目前**没有转化为位置收敛改善**。
2. 当前失败主因依然是位置收敛，replan 只是在局部目标层面重切分，未解决全局推进方向问题。
3. 下一步应把重点转向“目标生成策略”而不是“动作后处理”：
   - waypoint 不再直接来自 source states，改为从当前位姿到目标位姿的几何引导序列（例如直线+末段对齐）。
