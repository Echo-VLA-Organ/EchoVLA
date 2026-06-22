# Repository Packaging Guide

## 目标

在提交 `navgen` 仓库时，保留关键实验产物与复现实验文档，同时避免把体积大的二进制数据放进 git。

## 建议纳入版本库

- 配置与代码：`config/`, `controllers/`, `data_gen/`, `scripts/`, `utils/`
- 文档与报告：`docs/`, `reports/`
- 实验指标：`metrics/phase_a`, `metrics/phase_b`, `metrics/phase_d`
- 依赖与运行时规范：`requirements/`, `scripts/env/`, `config/runtime/`

## 建议不纳入版本库

- 原始/交付数据集：`datasets/**/*.hdf5`
- 本地运行日志：`logs/`
- 本地虚拟环境与依赖源码缓存：`.venv/`, `.deps/`

以上已通过 `.gitignore` 管控。

## 当前实验产物体积（参考）

- `metrics/phase_a`: `24K`
- `metrics/phase_b`: `2.0M`
- `metrics/phase_d`: `776K`（其中 `metrics/phase_d/r5`: `680K`）
- `reports/phase_a`: `4.0K`
- `reports/phase_b`: `24K`
- `reports/phase_d`: `44K`

总体指标与报告体积在可接受范围内（远小于常见仓库阈值）。

## 提交前检查

```bash
du -h metrics/phase_a metrics/phase_b metrics/phase_d reports/phase_a reports/phase_b reports/phase_d
git status --short
```

如需快速确认运行时可复现：

```bash
.venv/bin/python scripts/env/check_runtime.py --manifest config/runtime/runtime_manifest.yaml
```
