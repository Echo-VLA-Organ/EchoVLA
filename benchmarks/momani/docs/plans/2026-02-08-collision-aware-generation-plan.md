# Collision-Aware Data Generation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前生成流程从“仅终点成功”升级为“终点成功 + 碰撞可控”，把步级碰撞率压到可训练区间（先目标 < 5%）。

**Architecture:** 保持现有闭环控制器不大改，先增加碰撞审计与硬门禁（快速止血），再引入 obstacle-aware waypoint 生成（根因治理）。流程上分为“可观测性 -> 约束 -> 规划”三层，确保每层都有测试和回归命令。

**Tech Stack:** Python 3.10, unittest, h5py, numpy, robocasa/robosuite (MuJoCo contact)

---

### Task 1: 碰撞审计工具化（从一次性分析变成可复用脚本）

**Files:**
- Create: `navgen/utils/collision_metrics.py`
- Create: `navgen/scripts/phase_d/collision_audit.py`
- Test: `navgen/tests/test_collision_metrics.py`

**Step 1: Write the failing test**

```python
def test_count_mobile_contacts_only_counts_mobile_vs_non_mobile():
    contacts = [
        ("mobilebase0_pedestal_feet_col", "stack_handle"),
        ("mobilebase0_pedestal_feet_col", "mobilebase0_wheel"),
        ("counter_top", "stack_handle"),
    ]
    out = count_mobile_contacts(contacts, mobile_prefix="mobilebase0")
    assert out == 1
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest navgen/tests/test_collision_metrics.py`
Expected: FAIL with `ModuleNotFoundError` or `count_mobile_contacts not defined`

**Step 3: Write minimal implementation**

```python
def count_mobile_contacts(contact_pairs, mobile_prefix="mobilebase0"):
    n = 0
    for g1, g2 in contact_pairs:
        m1 = mobile_prefix in g1
        m2 = mobile_prefix in g2
        if m1 ^ m2:
            n += 1
    return n
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest navgen/tests/test_collision_metrics.py`
Expected: PASS

**Step 5: Commit**

```bash
git add navgen/utils/collision_metrics.py navgen/scripts/phase_d/collision_audit.py navgen/tests/test_collision_metrics.py
git commit -m "feat: add collision audit utilities for mobile-base contact tracking"
```

---

### Task 2: 生成摘要加入碰撞字段（先可观测）

**Files:**
- Modify: `navgen/scripts/phase_d/batch_generate.py`
- Modify: `navgen/utils/hdf5_utils.py`
- Test: `navgen/tests/test_hdf5_utils.py`

**Step 1: Write the failing test**

在 `test_hdf5_utils.py` 增加用例：`summarize_generation_metrics` 必须输出 `collision_step_rate`、`traj_collision_rate`。

```python
def test_summary_contains_collision_metrics(self):
    rows = [
        {"collision_steps": 5, "generated_traj_len": 10, "has_collision": True, "success": True, ...},
        {"collision_steps": 0, "generated_traj_len": 20, "has_collision": False, "success": True, ...},
    ]
    out = summarize_generation_metrics(rows)
    self.assertIn("collision_step_rate", out)
    self.assertIn("traj_collision_rate", out)
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest navgen/tests/test_hdf5_utils.py`
Expected: FAIL with missing collision keys

**Step 3: Write minimal implementation**

在 `summarize_generation_metrics` 中增加：
- `collision_steps_total`
- `steps_total`
- `collision_step_rate`
- `traj_collision_rate`

**Step 4: Run test to verify it passes**

Run: `python -m unittest navgen/tests/test_hdf5_utils.py`
Expected: PASS

**Step 5: Commit**

```bash
git add navgen/scripts/phase_d/batch_generate.py navgen/utils/hdf5_utils.py navgen/tests/test_hdf5_utils.py
git commit -m "feat: include collision metrics in phase-d generation summary"
```

---

### Task 3: 加入碰撞硬门禁（止血）

**Files:**
- Modify: `navgen/scripts/phase_d/batch_generate.py`
- Modify: `navgen/config/phase_b_control.yaml`
- Create: `navgen/config/tuning/phase_d_collision_gate.yaml`
- Test: `navgen/tests/test_phase_d_collision_gate.py`

**Step 1: Write the failing test**

```python
def test_collision_gate_marks_demo_failed_when_rate_exceeds_threshold():
    meta = apply_collision_gate(
        generated_traj_len=100,
        collision_steps=20,
        success=True,
        collision_step_rate_limit=0.05,
    )
    assert meta["success"] is False
    assert meta["stop_reason"] == "collision_gate"
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest navgen/tests/test_phase_d_collision_gate.py`
Expected: FAIL with missing `apply_collision_gate`

**Step 3: Write minimal implementation**

```python
def apply_collision_gate(generated_traj_len, collision_steps, success, collision_step_rate_limit):
    rate = collision_steps / max(generated_traj_len, 1)
    if rate > collision_step_rate_limit:
        return {"success": False, "stop_reason": "collision_gate", "collision_step_rate": rate}
    return {"success": success, "stop_reason": "success" if success else "unknown", "collision_step_rate": rate}
```

在 `_generate_one_demo` 返回字段中补充 `collision_steps`、`has_collision`、`collision_step_rate`。

**Step 4: Run test to verify it passes**

Run: `python -m unittest navgen/tests/test_phase_d_collision_gate.py`
Expected: PASS

**Step 5: Commit**

```bash
git add navgen/scripts/phase_d/batch_generate.py navgen/config/phase_b_control.yaml navgen/config/tuning/phase_d_collision_gate.yaml navgen/tests/test_phase_d_collision_gate.py
git commit -m "feat: add collision hard-gate for phase-d generation"
```

---

### Task 4: 引入 obstacle-aware waypoint 规划（根因治理）

**Files:**
- Create: `navgen/controllers/obstacle_waypoint_planner.py`
- Modify: `navgen/controllers/closed_loop_navigator.py`
- Modify: `navgen/scripts/phase_d/batch_generate.py`
- Test: `navgen/tests/test_obstacle_waypoint_planner.py`

**Step 1: Write the failing test**

```python
def test_planner_detours_around_blocking_rectangle():
    start = np.array([0.0, 0.0])
    goal = np.array([2.0, 0.0])
    obstacles = [((0.8, -0.4), (1.2, 0.4))]
    path = plan_2d_path(start, goal, obstacles, resolution=0.1)
    assert len(path) > 0
    assert any(abs(y) > 0.2 for _, y in path)
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest navgen/tests/test_obstacle_waypoint_planner.py`
Expected: FAIL with missing planner

**Step 3: Write minimal implementation**

先实现网格 A*（MVP），输入简单矩形障碍，输出 2D 路径点，再转为 base pose waypoint。

**Step 4: Run test to verify it passes**

Run: `python -m unittest navgen/tests/test_obstacle_waypoint_planner.py`
Expected: PASS

**Step 5: Commit**

```bash
git add navgen/controllers/obstacle_waypoint_planner.py navgen/controllers/closed_loop_navigator.py navgen/scripts/phase_d/batch_generate.py navgen/tests/test_obstacle_waypoint_planner.py
git commit -m "feat: add obstacle-aware waypoint planner for collision reduction"
```

---

### Task 5: 回归评估与验收报告

**Files:**
- Modify: `navgen/reports/phase_d/phase_d_execution.md`
- Create: `navgen/reports/phase_d/collision_reduction_eval.md`
- Modify: `navgen/metrics/phase_d/generation_summary.json`（重跑后更新）

**Step 1: Run baseline (current strategy) for comparison**

Run:

```bash
python navgen/scripts/phase_d/batch_generate.py --n 30 --output-hdf5 navgen/datasets/navgen/v1/demo_30_baseline.hdf5 --summary-output navgen/metrics/phase_d/generation_summary_30_baseline.json
```

Expected: 生成成功，得到 baseline 碰撞指标。

**Step 2: Run collision-aware strategy**

Run:

```bash
python navgen/scripts/phase_d/batch_generate.py --n 30 --output-hdf5 navgen/datasets/navgen/v1/demo_30_collision_aware.hdf5 --summary-output navgen/metrics/phase_d/generation_summary_30_collision_aware.json --waypoint-mode obstacle_aware
```

Expected: `collision_step_rate` 明显下降，成功率不显著劣化。

**Step 3: Validate generated dataset**

Run:

```bash
python navgen/scripts/phase_d/training_validation.py --input navgen/datasets/navgen/v1/demo_30_collision_aware.hdf5 --json-output navgen/metrics/phase_d/training_validation_30_collision_aware.json
```

Expected: `pass: true` 且 `action_oob_count: 0`。

**Step 4: Document and acceptance gate**

在报告中写明：
- baseline vs collision-aware 的 `success_rate / collision_step_rate / traj_collision_rate`
- 是否达到阈值：`collision_step_rate < 0.05`，`success_rate >= 0.75`

**Step 5: Commit**

```bash
git add navgen/reports/phase_d/phase_d_execution.md navgen/reports/phase_d/collision_reduction_eval.md navgen/metrics/phase_d/*.json
git commit -m "docs: add collision reduction evaluation and updated phase-d gates"
```
