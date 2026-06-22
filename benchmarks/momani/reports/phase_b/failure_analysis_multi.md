# Phase B 多批次失败分析

## 总体结果
- 批次数: 4
- 样本数: 40
- 成功率: 0.000
- 命中 max_steps 比例: 0.825
- 平均终点位置误差: 2.456 m
- 平均终点朝向误差: 11.31 deg
- 平均 waypoint 到达数: 3.90
- 平均 waypoint 超时数: 8.60

## 失败类型
- pos_and_yaw_not_converged: 13
- pos_not_converged: 27

## 每批次摘要
- /Users/candlest/dev/navgen/metrics/phase_b/closed_loop_eval_10_s0.json: success_rate=0.000, avg_pos_err=2.690, avg_yaw_err=10.33, avg_gen_len=483.2
- /Users/candlest/dev/navgen/metrics/phase_b/closed_loop_eval_10_s10.json: success_rate=0.000, avg_pos_err=1.491, avg_yaw_err=10.77, avg_gen_len=495.3
- /Users/candlest/dev/navgen/metrics/phase_b/closed_loop_eval_10_s20.json: success_rate=0.000, avg_pos_err=2.617, avg_yaw_err=13.58, avg_gen_len=483.2
- /Users/candlest/dev/navgen/metrics/phase_b/closed_loop_eval_10_s30.json: success_rate=0.000, avg_pos_err=3.025, avg_yaw_err=10.56, avg_gen_len=475.7

## 首轮调参建议
1. 先降低任务难度：仅测试前 5 个 waypoint，确认单段闭环能稳定收敛
2. 减少 waypoint 数量：将 step_interval 从 10 提到 20，优先验证终点收敛
3. 提升每步推进能力：smoothing.alpha 从 0.30 降到 0.15，减小动作迟滞
4. 放宽 waypoint 到达阈值：reached_threshold_m 从 0.15 放宽到 0.22
5. 暂时降低门控保守性：ori_priority_threshold_deg 从 17 提到 25
6. 位置收敛是主瓶颈：先加大平移推进（vx_max 0.8->1.0, vy_max 0.6->0.8）
7. 减速触发更晚：deceleration.distance_threshold_m 从 0.50 降到 0.25
