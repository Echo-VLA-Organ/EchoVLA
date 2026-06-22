# Phase B 调参 Round-1 记录

## 运行组合

- baseline: `closed_loop_eval_20_baseline.json`
- tune-a: `closed_loop_eval_20_tune_a.json`
- tune-b: `closed_loop_eval_20_tune_b.json`
- tune-b-target-only: `closed_loop_eval_20_tune_b_target_only.json`

## 关键对比

| run | success_rate | avg_final_pos_error(m) | avg_final_yaw_error(deg) | avg_generated_len |
|---|---:|---:|---:|---:|
| baseline | 0.00 | 2.078 | 10.55 | 489.3 |
| tune-a | 0.00 | 2.199 | 4.83 | 294.4 |
| tune-b | 0.00 | 2.427 | 2.36 | 212.0 |
| tune-b-target-only | 0.00 | 2.561 | 4.68 | 464.2 |

## 失败形态结论

1. **核心瓶颈是位置收敛，不是朝向收敛**
   - tune-a / tune-b 明显降低 yaw 误差，但 pos 误差没有改善。
   - 40 条统计里 `pos_not_converged` 与 `pos_and_yaw_not_converged` 占全部失败。

2. **轨迹预算被大量消耗在 waypoint 超时上**
   - baseline 多批次平均 `timeout_waypoints ~= 8.6`。
   - 即使 tune-b 缩短轨迹长度，成功率仍为 0。

3. **直接终点模式（target-only）无效**
   - yaw 对齐很快，但 pos 误差仍停留在 1~4m 区间，说明仅面向最终目标会被场景几何约束卡住。

## 下一轮调参方向（Round-2）

1. 先恢复 waypoint 路线，但加入“**局部进度保底**”机制：
   - 每个 waypoint 不再硬超时跳过；若 15 步内 pos_error 不下降，则切分成中间子目标再推进。

2. 引入“**末段锁定**”仅用于最后 1~2 个 waypoint，而不是全局使用。

3. 新增调试指标并写入 step_trace：
   - `delta_pos_error_per_10_steps`
   - `stuck_counter`
   - `base_action_norm`

4. Round-2 A/B 建议：
   - A: 保守恢复（step_interval=15, smoothing=0.2）
   - B: 激进推进（step_interval=12, smoothing=0.0, stuck_replan 开启）
