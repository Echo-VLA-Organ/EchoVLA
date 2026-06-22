# NavigateKitchen 开环失败归因报告 (10 demos)

## 总览
- 样本数: 10
- 成功数: 0
- 失败数: 10
- 失败类型统计:
  - early_heading_bias: 7
  - mid_drift: 3
  - late_alignment_failure: 0

## 分类规则
- pos_success_th: 0.2 m
- yaw_success_deg: 11.5 deg
- early_step_th: 5 steps
- severe_pos_err_th: 2.5

## 早期偏航
- demo_0: div_step=0, max_state_err=2.743, pos_err=2.736, yaw_err_deg=20.21, layout=2, style=4, lang=navigate to the shelves
- demo_1: div_step=0, max_state_err=3.191, pos_err=3.158, yaw_err_deg=23.09, layout=3, style=7, lang=navigate to the oven
- demo_3: div_step=0, max_state_err=2.800, pos_err=2.887, yaw_err_deg=59.59, layout=6, style=7, lang=navigate to the microwave

## 中段漂移
- demo_2: div_step=0, max_state_err=1.772, pos_err=1.786, yaw_err_deg=0.47, layout=8, style=2, lang=navigate to the toaster
- demo_4: div_step=0, max_state_err=1.718, pos_err=1.777, yaw_err_deg=0.26, layout=9, style=2, lang=navigate to the stove
- demo_5: div_step=0, max_state_err=2.444, pos_err=2.566, yaw_err_deg=0.00, layout=2, style=8, lang=navigate to the coffee machine

## 末段对齐失败
- 无样例

## 结论
- 当前开环回放在首段就出现状态偏离，闭环控制为必要路径。
- 下一步建议直接进入 Phase B：子目标闭环控制与场景固定管道。
