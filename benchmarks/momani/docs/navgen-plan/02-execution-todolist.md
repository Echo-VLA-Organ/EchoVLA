# NavigateKitchen 执行 TodoList

## 使用说明
- 状态定义: `pending` / `in_progress` / `done` / `blocked`。
- 原则: 同时仅 1 个 `in_progress` 的主任务。
- 目标: 先拿到稳定成功率，再扩规模。

## Phase A - 基线与数据语义 (Day 1)
- [ ] A1. 数据结构锁定
  - 产出: data schema note
  - 验收: 明确 `actions[:, 7:10]` 是 base，`states=[time,qpos,qvel]`。
- [ ] A2. 开环 replay 基线 (10 demos)
  - 产出: 成功率、终点误差、发散步统计。
  - 验收: 形成可复现 baseline 表。
- [ ] A3. 失败类型归因
  - 产出: 失败类型字典 (早期偏航/中段漂移/末段对齐失败)。
  - 验收: 每类至少 2 个样例。

## Phase B - 闭环最小可用 (Day 2-3)
- [ ] B1. 实现闭环 base 控制
  - 输入: 当前位姿、目标位姿。
  - 输出: base action (vx, vy, wz) + base_mode。
  - 验收: 单 scene 下 10 条成功率明显高于开环。
- [ ] B2. 固定 scene 管道接入
  - 验收: 每条生成轨迹记录 source demo 的 layout/style/fixture。
- [ ] B3. 最小可视化回放
  - 验收: 能快速抽检轨迹是否走向目标而非漂移。

## Phase C - 恢复机制与稳态 (Day 4)
- [ ] C1. 误差门控
  - 规则: 角度误差大先转向，位置误差大再平移。
  - 验收: 末段失败率下降。
- [ ] C2. 速度/角速度限幅
  - 验收: 消除振荡与来回抖动。
- [ ] C3. 参数扫描
  - 参数: 位置增益、角度增益、减速阈值。
  - 验收: 得到一组默认稳定参数。

## Phase D - 扩规模与验收 (Day 5)
- [ ] D1. 生成 100 条新 demo
  - 验收: 成功率 >= 75%。
- [ ] D2. 生成元数据与失败日志
  - 字段: source_demo, layout_id, style_id, seed, stop_reason, final_error。
- [ ] D3. 训练可用性抽检
  - 验收: 轨迹分布合理，无系统性异常。

## 强制检查点
- [ ] 每日 checkpoint-1 (中午): 更新当前指标与 blocker。
- [ ] 每日 checkpoint-2 (晚上): 更新成功率曲线与次日计划。

## DoD (Definition of Done)
- [ ] 可复现: 新环境按文档能复跑出同级结果。
- [ ] 可追溯: 每条结果可定位到参数与场景。
- [ ] 可扩展: 能无缝从 100 条扩展到更大规模。
