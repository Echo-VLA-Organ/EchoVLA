# Phase B Round-4 Continued（默认策略持续推进）

## 本轮追加动作

- 修复评估逻辑缺陷：`runaway_max_events=0` 时不再误记 `aborted_waypoints`。
- 在 `test_closed_loop.py` 增强控制逻辑：
  - 两阶段控制（translate / align）
  - 跑飞检测与恢复（runaway guard）
  - 记录新增指标：`runaway_events`, `aborted_waypoints`
- 新增多组参数实验：A、C_fix、D、E、F、G(no_mg)

## 关键结果（20 demos, start=0）

| run | success_rate | avg_pos_err(m) | avg_yaw_err(deg) | avg_len | 备注 |
|---|---:|---:|---:|---:|---|
| round4_A | 0.05 | 2.761 | 9.70 | 249.9 | 当前最佳之一 |
| round4_C_control_fix | 0.05 | 2.916 | 7.05 | 307.9 | 对照修复后 |
| round4_D_plus | 0.00 | 3.263 | 19.94 | 479.8 | 过激参数，退化 |
| round4_E_plus_replan | 0.00 | 2.972 | 6.29 | 494.0 | 步数膨胀 |
| round4_F_source_pos_only | 0.00 | 2.679 | 31.74 | 445.5 | source位置优先失败 |
| round4_G_no_mg | 0.05 | 2.787 | 2.54 | 250.8 | 禁用mg后稳定但仍低成功 |

## 失败原因更新

1. 主瓶颈仍是 **位置收敛**（大量样本停留在 1~4m 区间）。
2. 少数样本存在严重跑飞（例如 `demo_11` 可达到 9m+），跑飞保护只能止损，尚未转化为成功提升。
3. 提高 replan / lock 强度会显著拉长轨迹，但成功率未提升。

## 结论

- 现有“参数调优 + 局部保护”已接近上限，继续微调收益很小。
- 下一步应切换到 **路径策略升级**：
  1. 引入可行路径中间点（基于厨房可行走区域的2D规划，而非直线几何点）
  2. 再用当前闭环控制器去跟踪该路径
