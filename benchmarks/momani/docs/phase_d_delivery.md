# Phase D 数据交付

## 目标

把原始生成集按碰撞约束筛成可交付子集，支持三档轨迹碰撞率阈值：

- `0`
- `0.1`
- `0.2`

并按指定数量交付，样本不足时严格失败（不自动放宽阈值，不重复采样）。

## 脚本

- `scripts/phase_d/deliver_dataset.py`

关键参数：

- `--input-hdf5`：原始生成数据集
- `--output-hdf5`：交付数据集
- `--target-count`：交付数量
- `--traj-collision-threshold`：仅允许 `0 / 0.1 / 0.2`
- `--summary-output`：交付报告 JSON
- `--success-only`：仅从 success 样本中挑选（默认开启）
- `--dry-run`：只评估，不写 hdf5

## 示例

```bash
.venv/bin/python scripts/phase_d/deliver_dataset.py \
  --input-hdf5 datasets/navgen/v1/r5/r5_g4_rcvenv_n90.hdf5 \
  --output-hdf5 datasets/navgen/v1/r5/r5_g4_rcvenv_n90_delivery_t00_n20.hdf5 \
  --target-count 20 \
  --traj-collision-threshold 0 \
  --summary-output metrics/phase_d/r5/r5_g4_rcvenv_n90_delivery_t00_n20_summary.json
```

```bash
.venv/bin/python scripts/phase_d/deliver_dataset.py \
  --input-hdf5 datasets/navgen/v1/r5/r5_g4_rcvenv_n90.hdf5 \
  --output-hdf5 datasets/navgen/v1/r5/r5_g4_rcvenv_n90_delivery_t01_n30.hdf5 \
  --target-count 30 \
  --traj-collision-threshold 0.1 \
  --summary-output metrics/phase_d/r5/r5_g4_rcvenv_n90_delivery_t01_n30_summary.json
```

```bash
.venv/bin/python scripts/phase_d/deliver_dataset.py \
  --input-hdf5 datasets/navgen/v1/r5/r5_g4_rcvenv_n90.hdf5 \
  --output-hdf5 datasets/navgen/v1/r5/r5_g4_rcvenv_n90_delivery_t02_n30.hdf5 \
  --target-count 30 \
  --traj-collision-threshold 0.2 \
  --summary-output metrics/phase_d/r5/r5_g4_rcvenv_n90_delivery_t02_n30_summary.json
```

## 严格失败行为

当阈值下无法凑满 `target-count` 时，脚本直接失败，并在 summary 里写入：

- 当前可用样本数
- 需要的无碰撞样本下限
- 推荐原始生成量 `recommended_raw_count`

示例：`metrics/phase_d/r5/r5_g4_rcvenv_n90_delivery_t00_n40_summary.json`
