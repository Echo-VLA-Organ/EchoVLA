# Phase B 调参 Round-3（Geometric Waypoints）

## 本轮实现

- 在 `navgen/controllers/closed_loop_navigator.py` 新增几何 waypoint 生成：
  - `extract_geometric_waypoints_to_target(target_pose, segment_length_m, min_waypoints, max_waypoints)`
  - 中间 waypoint 采用“沿直线前进朝向”，最后 waypoint 采用目标朝向。
- 在 `navgen/scripts/phase_b/test_closed_loop.py` 新增参数：
  - `--waypoint-mode {source_states,geometric,geometric_to_target}`
  - `--geometric-segment-m`
  - `--geometric-min-waypoints`
  - `--geometric-max-waypoints`

## Round-3 A/B 结果（20 demos, start=0）

| 模式 | success_rate | avg_final_pos_error(m) | avg_final_yaw_error(deg) | avg_generated_len |
|---|---:|---:|---:|---:|
| source_states | 0.00 | 2.502 | 5.36 | 392.9 |
| geometric | 0.05 | 2.883 | 7.06 | 303.9 |

补充阈值统计：
- source_states: `pos<=0.2` 命中 0 / 20，`yaw<=11.5` 命中 14 / 20
- geometric: `pos<=0.2` 命中 1 / 20，`yaw<=11.5` 命中 19 / 20

## 结论

1. 几何 waypoint 路线首次出现成功样本（1/20），方向正确。
2. 位置收敛仍是主要瓶颈，且存在极端失败样本（例如 `demo_11` 位置误差 11.686m）。
3. 几何模式在保持较好 yaw 收敛的同时，轨迹长度明显降低（约 393 -> 304）。

## 下一步（Round-4 建议）

1. 引入异常保护：当 `pos_error` 连续上升并超过 5m，立即 reset 当前 waypoint 策略（避免跑飞）。
2. 几何路线分两段：
   - 第一段只追位置（忽略 yaw）
   - 末段（距离目标 < 0.6m）再强制朝向收敛
3. 对失败重灾 demo（如 `demo_3`, `demo_6`, `demo_9`, `demo_10`, `demo_11`）单独做 debug 组。
