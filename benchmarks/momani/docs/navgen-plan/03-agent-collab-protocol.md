# Multi-Agent 协作协议 (NavigateKitchen)

## 1. 协作目标
- 让多个 agent 并行推进且不互相覆盖，最终收敛到高成功率生成链路。

## 2. 角色分工
- Agent A (Data): 数据语义、统计、基线报告。
- Agent B (Control): 闭环控制与恢复策略实现。
- Agent C (Eval): 指标评测、分桶分析、可视化抽检。
- Coordinator: 合并决策、冻结参数、发布里程碑结论。

## 3. 文件 Ownership
- Agent A 只改: `analysis/*`, `reports/*`, 数据检查脚本。
- Agent B 只改: 导航控制与执行逻辑代码。
- Agent C 只改: 评估脚本、报表模板、可视化工具。
- 共享配置文件只能由 Coordinator 合并。

## 4. 输入输出契约
- 输入数据: 官方 `demo.hdf5` (只读，不重写)。
- 中间产物: prepared dataset, logs, metrics json。
- 输出规范:
  - `metrics/*.json`: 固定字段 (`success_rate`, `n_trials`, `layout_bucket`, `style_bucket`, `final_pos_err`, `final_yaw_err`)
  - `reports/*.md`: 结论先行，附关键图表或统计表。

## 5. 分支与合并规则
- 分支命名:
  - `feat/navgen-data-*`
  - `feat/navgen-control-*`
  - `feat/navgen-eval-*`
- PR 必备:
  - 变更说明
  - 复现命令
  - 前后指标对比
- 禁止:
  - 无指标的“感觉优化”直接合并
  - 覆盖他人 ownership 文件

## 6. 评审门禁
- Gate-1: 功能正确 (可运行)。
- Gate-2: 指标提升 (至少一个核心指标改善且无严重回退)。
- Gate-3: 稳定性检查 (分 layout/style 不失控)。

## 7. 同步节奏
- 每日 2 次同步:
  - Noon Sync: 当前进度、阻塞、当日风险。
  - EOD Sync: 指标快照、合并建议、次日计划。
- 阻塞升级: blocker > 2 小时即上报 Coordinator。

## 8. 快速决策规则
- 若开环与闭环冲突: 以成功率目标优先，默认闭环。
- 若指标互有取舍: 先保成功率，再调轨迹平滑度。
- 若同类方案并存: 采用 A/B 小样本 20 条对比后决策。

## 9. 统一实验模板
- 固定随机种子列表。
- 固定 demo 子集用于回归测试。
- 固定输出目录结构:
  - `runs/<date>/<exp_name>/config.json`
  - `runs/<date>/<exp_name>/metrics.json`
  - `runs/<date>/<exp_name>/log.txt`

## 10. 交付标准
- 技术交付: 代码 + 配置 + 数据生成脚本。
- 结果交付: 指标表 + 失败案例归因 + 下一步建议。
- 文档交付: 能让新 agent 在 30 分钟内接手。
