# MoMani Benchmark

NavigateKitchen closed-loop data generation and evaluation.

## Dataset formats

| Format | Example path |
|--------|----------------|
| RoboCasa365 LeRobot | `.../robocasa365-datasets/pretrain/atomic/NavigateKitchen/20250821/lerobot` |
| Legacy HDF5 | `.../NavigateKitchen/demo.hdf5` |

Set `ECHO_MOMANI_DATASET` or `ECHO_ROBOCASA365_DATA` (see `env.example`).

## Commands

```bash
# From repo root
source scripts/bootstrap_momani_echo.sh

python eval_momani.py closed_loop --n 10 --dataset /path/to/lerobot/root
python eval_momani.py closed_loop --nav-stitch --stitch-length 3 --n 5
python eval_momani.py deliver --input-hdf5 raw.hdf5 --target-count 30 --traj-collision-threshold 0.1
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `ECHO_MOMANI_ROOT` | MoMani root (`benchmarks/momani`) |
| `ECHO_MOMANI_DATASET` | HDF5 or LeRobot task directory |
| `ECHO_ROBOCASA365_DATA` | RoboCasa365 datasets root |
| `ECHO_MOMANI_OFFICIAL_HDF5` | Legacy NavigateKitchen HDF5 |
| `ROBOCASA_SRC` / `ROBOSUITE_SRC` | Simulation forks (or use `bootstrap_runtime.sh`) |
