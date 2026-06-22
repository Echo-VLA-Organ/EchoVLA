# EchoVLA — MoMani Benchmark

Open-source **MoMani** benchmark for RoboCasa `NavigateKitchen`: closed-loop navigation evaluation, data generation, and multi-leg nav stitching.

This repository contains **only the benchmark toolchain** (not the full Echo-VLA training stack).

## Features

- **NavigateKitchen** closed-loop eval (Phase B) and dataset delivery (Phase D)
- **Dual dataset format**: legacy HDF5 + [RoboCasa365](https://huggingface.co/datasets/robocasa/robocasa365) LeRobot
- **Nav stitching**: chain multiple navigation targets in the same kitchen layout

## Quick start

```bash
git clone https://github.com/Echo-VLA-Organ/EchoVLA.git
cd EchoVLA
source scripts/setup_env.sh
source scripts/bootstrap_momani_echo.sh

# Runtime (robosuite + robocasa via uv)
benchmarks/momani/scripts/env/bootstrap_runtime.sh

# Closed-loop eval (RoboCasa365 LeRobot)
export ECHO_ROBOCASA365_DATA=/path/to/robocasa365-datasets
python eval_momani.py closed_loop --n 10 \
  --dataset ${ECHO_ROBOCASA365_DATA}/pretrain/atomic/NavigateKitchen/20250821/lerobot

# Multi-leg nav stitching
python eval_momani.py closed_loop --nav-stitch --stitch-length 3 --n 5
```

## Layout

```
EchoVLA/
├── eval_momani.py          # Entry point
├── benchmarks/momani/      # MoMani core (controllers, scripts, tests)
├── utils/momani_bridge.py  # Dataset path resolution
└── scripts/                # Environment bootstrap
```

## Tests

```bash
cd benchmarks/momani
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Docs

See [benchmarks/README.md](benchmarks/README.md) and `benchmarks/momani/docs/`.

## License

See `benchmarks/momani/LICENSE` if present; otherwise contact the maintainers.
