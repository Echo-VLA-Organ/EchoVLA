# Runtime 规范与部署

## 目标

为 `navgen` 提供可跨平台（WSL/Linux + macOS）的可复现运行时，不依赖本机绝对路径。

## 规范文件

- 运行时清单：`config/runtime/runtime_manifest.yaml`
- 通用依赖：`requirements/runtime-core.txt`
- Linux/WSL 依赖：`requirements/runtime-platform-linux-wsl.txt`
- macOS 依赖：`requirements/runtime-platform-darwin.txt`
- 源码依赖固定版本：`requirements/runtime-sources.txt`
- 自检脚本：`scripts/env/check_runtime.py`
- bootstrap 脚本：`scripts/env/bootstrap_runtime.sh`

## 一键部署

在 `navgen` 根目录运行：

```bash
scripts/env/bootstrap_runtime.sh
```

默认行为：

- 在仓库内创建 `.venv`
- 在仓库内创建 `.deps` 并拉取依赖源码
- 安装跨平台依赖与源码包
- 执行 `check_runtime.py` 校验

## 常用环境变量

- `NAVGEN_VENV_PATH`：指定虚拟环境路径
- `NAVGEN_DEPS_ROOT`：指定依赖源码目录
- `NAVGEN_PYTHON_VERSION`：默认 `3.10`
- `NAVGEN_SKIP_GIT_SYNC=1`：跳过 git fetch / checkout（使用现有源码目录）
- `NAVGEN_ROBOCASA_GIT_URL` / `NAVGEN_ROBOCASA_GIT_REF`
- `NAVGEN_ROBOSUITE_GIT_URL` / `NAVGEN_ROBOSUITE_GIT_REF`

若你有自定义本地源码路径，也可直接设置：

- `ROBOCASA_SRC`
- `ROBOSUITE_SRC`

可选（仅在你想使用外部 MimicGen fallback 时）：

- `MIMICGEN_SRC` 或 `NAVGEN_MIMICGEN_SRC`

## 运行时验证

```bash
.venv/bin/python scripts/env/check_runtime.py \
  --manifest config/runtime/runtime_manifest.yaml
```

说明：该校验只检查运行时与依赖，不检查数据集路径。`config/base_config.yaml` 里的数据集路径需在新机器上单独配置。
默认模板已使用相对路径 `datasets/official/NavigateKitchen/demo.hdf5`，可按本机实际位置修改或通过脚本参数 `--dataset` 覆盖。

严格校验解释器路径（仅在固定路径场景需要）：

```bash
.venv/bin/python scripts/env/check_runtime.py \
  --manifest config/runtime/runtime_manifest.yaml \
  --strict-executable
```

## WSL 建议

- 推荐 Ubuntu 22.04+
- 使用仓库内 `.venv`，避免复用宿主机 Python
- navgen 默认内置 `MGNavigateKitchenLite`，不强依赖外部 `mg_navigate`。
- 如需强制使用你自己的 MimicGen 分支，请把源码路径传给 `MIMICGEN_SRC` 或 `NAVGEN_MIMICGEN_SRC`。
