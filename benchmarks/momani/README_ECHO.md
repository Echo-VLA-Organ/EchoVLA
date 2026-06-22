# MoMani in Echo_VLA

This directory contains the vendored NavigateKitchen benchmark toolchain.

Echo_VLA integration:

- Portable config: `config/echo_base_config.yaml`
- Bootstrap: `source ../../scripts/bootstrap_momani_echo.sh` (from Echo_VLA root)
- Eval entry: `python ../../eval_momani.py closed_loop --n 10`

See `../README.md` for full setup (runtime venv, deliver pipeline).

Docs: `docs/`, `docs/phase_d_delivery.md`, `docs/repository_packaging.md`.
