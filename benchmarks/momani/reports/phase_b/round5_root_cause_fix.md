# Phase B Round-5：根因修复与结果

## 根因结论

通过动作轴诊断，我们确认了核心问题不是调参，而是 **base 动作轴映射错误**：

- 我们一直按逻辑顺序 `[vx, vy, wz]` 组装 base action。
- 真实环境中 base 控制器期望顺序是 **`[vy, vx, wz]`**（x / y 交换）。
- 这个错误会导致机器人长期沿错误方向推进，表现为：
  - 位置误差持续增大
  - 朝向误差可收敛但位置始终失败
  - 参数调优对成功率几乎无效

## 修复内容

1. 在 `navgen/controllers/closed_loop_navigator.py` 新增：
   - `map_base_action_for_env()`
   - 配置项 `base_action_order` / `base_action_sign`
   - 默认映射设为 `[1, 0, 2]`
2. 禁用默认 mg target 转换路径：
   - `use_mg_target_to_action: false`
3. 增加单元测试：
   - `navgen/tests/test_base_action_mapping.py`

## 评估结果

### 关键评估（90 demos）

- 文件：`metrics/phase_b/closed_loop_eval_90_round5_precision.json`
- 结果：
  - `success_rate = 0.8778` (79 / 90)
  - `avg_final_pos_error = 0.376 m`
  - `avg_final_yaw_error_deg = 3.01`
  - `avg_generated_traj_len = 228.6`

### 分批结果（20 demos）

- `closed_loop_eval_20_round5_precision_s0.json`: `0.65`
- `closed_loop_eval_20_round5_precision_s20.json`: `0.85`
- `closed_loop_eval_20_round5_precision_s40.json`: `0.85`

## 当前推荐配置

- `config/phase_b_control.yaml` 已更新为推荐默认：
  - `waypoint.mode = geometric_to_target`
  - `controller.base_action_order = [1, 0, 2]`
  - `controller.reached_threshold_m = 0.19`
  - `controller.reached_yaw_deg = 11.0`

## 结论

Round-5 已完成从“低成功率调参期”到“高成功率可用期”的转变。下一步可进入 Phase D：批量生成 100 条并输出元数据与失败日志。
