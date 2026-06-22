# MoMani (NavigateKitchen)

面向 RoboCasa `NavigateKitchen` 的闭环数据生成与交付工具链。

## 当前状态

- 已完成 Phase D 批量生成与碰撞审计流程。
- 已提供“按碰撞阈值 + 指定数量”的交付脚本：`scripts/phase_d/deliver_dataset.py`。
- 当前交付策略支持阈值：`0 / 0.1 / 0.2`，并在样本不足时严格失败。

## 目录说明

- `config/`: 生成控制参数与运行时规范
- `controllers/`: 闭环控制与 waypoint 规划
- `data_gen/`: 场景固定与环境重建
- `scripts/phase_*`: 各阶段脚本
- `scripts/env/`: 运行时自检与 bootstrap
- `utils/`: 指标、筛选、HDF5 工具
- `docs/`: 使用文档与计划
- `reports/`, `metrics/`, `logs/`: 结果输出

## 运行时规范（.venv）

默认解释器路径：`./.venv/bin/python`（由 `scripts/env/bootstrap_runtime.sh` 创建）

运行时自检：

```bash
.venv/bin/python scripts/env/check_runtime.py \
  --manifest config/runtime/runtime_manifest.yaml
```

如需重建可部署环境：

```bash
scripts/env/bootstrap_runtime.sh
```

常见覆盖参数（用于他机部署）：

- `NAVGEN_ROBOCASA_GIT_URL` / `NAVGEN_ROBOCASA_GIT_REF`
- `NAVGEN_ROBOSUITE_GIT_URL` / `NAVGEN_ROBOSUITE_GIT_REF`
- `NAVGEN_SKIP_GIT_SYNC=1`（使用本地已有源码）

可选（仅在需要外部 MimicGen fallback 时）：

- `NAVGEN_MIMICGEN_SRC` 或 `MIMICGEN_SRC`

MoMani 默认内置 `MGNavigateKitchenLite`，不再强依赖外部 `mg_navigate` 模块。

跨平台依赖文件：

- `requirements/runtime-core.txt`
- `requirements/runtime-platform-linux-wsl.txt`
- `requirements/runtime-platform-darwin.txt`
- `requirements/runtime-sources.txt`

数据路径提示：

- `config/base_config.yaml` 中 `paths.official_dataset_hdf5` 默认是模板相对路径。
- 部署到新机器后，请改为你的本地路径，或在运行脚本时显式传 `--dataset`。

## 数据交付（按碰撞阈值）

脚本：`scripts/phase_d/deliver_dataset.py`

参数：

- `--input-hdf5` 原始生成数据
- `--output-hdf5` 交付数据
- `--target-count` 交付数量
- `--traj-collision-threshold` 仅允许 `0 / 0.1 / 0.2`
- `--summary-output` 交付报告
- `--dry-run` 仅评估

示例（阈值 0.1，交付 30 条）：

```bash
.venv/bin/python scripts/phase_d/deliver_dataset.py \
  --input-hdf5 datasets/momani/v1/r5/r5_g4_rcvenv_n90.hdf5 \
  --output-hdf5 datasets/momani/v1/r5/r5_g4_rcvenv_n90_delivery_t01_n30.hdf5 \
  --target-count 30 \
  --traj-collision-threshold 0.1 \
  --summary-output metrics/phase_d/r5/r5_g4_rcvenv_n90_delivery_t01_n30_summary.json
```

补充说明见：`docs/phase_d_delivery.md`

仓库打包与产物纳入策略见：`docs/repository_packaging.md`

## 注意

- 不使用系统 Python 进行依赖安装。
- 依赖管理统一走 `uv`。
