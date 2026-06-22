# NavigateKitchen 数据生成总体策略

## 1. 目标与范围
- 目标: 基于 RoboCasa 官方 NavigateKitchen 数据集，构建可复现的高成功率新 demo 生成流程。
- 优先级: 先成功率，再规模化；先稳定，再提速。
- 范围: 单任务 `NavigateKitchen`，数据源固定为官方 `human_raw`。

## 2. 已确认的关键事实
- 官方数据集路径: `/Users/candlest/dev/robocasa/datasets/v0.1/single_stage/kitchen_navigate/NavigateKitchen/2024-05-09/demo.hdf5`。
- 数据结构: 顶层为 `data` 和 `mask`。每条 demo 含 `states` 与 `actions`。
- `states` 语义: MuJoCo flatten 状态，即 `[time, qpos, qvel]`。
- `actions` 维度: 12 维。
  - `0:6` 机械臂
  - `6:7` gripper
  - `7:10` base (导航核心)
  - `10:11` torso
  - `11` base_mode
- 控制器来源: `default_pandaomron.json` 使用 `HYBRID_MOBILE_BASE`，base 为 `JOINT_VELOCITY`。

## 3. 问题本质
- 长轨迹开环 action replay 容易累计误差，导致后期偏离目标。
- 官方回放脚本本身也对发散做了告警处理，说明这不是单点异常。
- 结论: 单纯开环 replay 不是高成功率路线，应转闭环控制。

## 4. 技术路线
- 路线 A (基线): 官方动作开环 replay，量化失败模式。
- 路线 B (主线): 基于当前状态误差的闭环 base 控制。
- 路线 C (增强): 误差恢复机制 + 参数扫描 + 分布局验证。

## 5. 数据生成设计
- 固定 scene: 导航任务必须保持 source demo 的 `ep_meta` (layout/style/fixture refs)。
- 轨迹驱动: 使用 `target_pose` 或子目标序列，逐步闭环求 base action。
- action 组装: 仅写 `base` slice (`7:10`) 与必要 `base_mode`，其它维度保持安全默认。
- 成功判定: 以环境 `is_success` / `_check_success` 为唯一准则。

## 6. 评估指标 (KPI)
- 成功率: 10 条小样本 >= 60%，100 条 >= 75%。
- 终点误差: 位置与朝向误差分布可解释，尾部受控。
- 稳定性: 不同 layout/style 下无明显单桶崩溃。

## 7. 风险与缓解
- 风险: 场景切换导致隐式目标变化。
  - 缓解: 严格固定 `ep_meta`，日志记录每次 layout/style。
- 风险: 闭环增益过大引发振荡。
  - 缓解: 分段控制 (先朝向后平移)、速度限幅、末段减速。
- 风险: 多 agent 并行改动冲突。
  - 缓解: 文件 ownership + PR 门禁 + 指标快照。

## 8. 里程碑
- M1: 完成数据语义与基线报告。
- M2: 闭环最小可用版本达到显著提升。
- M3: 参数稳态后生成 100+ 条新 demo。
- M4: 形成可复现 runbook 与协作规范。

## 9. 关键代码定位
- `robocasa/scripts/collect_demos.py` (states/actions 记录时序说明)
- `robocasa/scripts/playback_dataset.py` (回放发散检查)
- `robosuite/controllers/composite/composite_controller.py` (base_mode 追加到 action 最后一维)
- `robosuite/controllers/config/robots/default_pandaomron.json` (控制器配置)
- `mimicgen/env_interfaces/robocasa/single_stage/mg_navigate.py` (导航接口转换逻辑)
