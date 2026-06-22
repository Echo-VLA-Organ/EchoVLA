"""Unified dataset backends for MoMani (HDF5 + RoboCasa365 LeRobot)."""

from __future__ import annotations

import gzip
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class DemoRecord:
    demo_id: str
    episode_index: int
    layout_id: Optional[int]
    style_id: Optional[int]
    lang: str
    target_fixture: Optional[str]
    length: int


def _decode(v: Any) -> Any:
    if isinstance(v, bytes):
        return v.decode("utf-8")
    return v


def detect_dataset_format(dataset_path: str | Path) -> str:
    """Return ``hdf5`` or ``lerobot365``."""
    path = Path(os.path.expanduser(str(dataset_path))).resolve()
    if path.is_file() and path.suffix.lower() in {".hdf5", ".h5"}:
        return "hdf5"
    if path.is_dir():
        if (path / "meta" / "info.json").is_file():
            return "lerobot365"
        if (path / "lerobot" / "meta" / "info.json").is_file():
            return "lerobot365"
        for child in path.iterdir():
            if child.is_dir() and (child / "meta" / "info.json").is_file():
                return "lerobot365"
    raise ValueError(f"Unsupported or missing dataset path: {path}")


def resolve_lerobot_root(dataset_path: str | Path) -> Path:
    path = Path(os.path.expanduser(str(dataset_path))).resolve()
    if (path / "meta" / "info.json").is_file():
        return path
    if (path / "lerobot" / "meta" / "info.json").is_file():
        return path / "lerobot"
    for child in sorted(path.iterdir()):
        if child.is_dir() and (child / "meta" / "info.json").is_file():
            return child
    raise ValueError(f"LeRobot root not found under: {path}")


def open_dataset_backend(dataset_path: str | Path) -> "BaseDatasetBackend":
    fmt = detect_dataset_format(dataset_path)
    if fmt == "hdf5":
        return Hdf5DatasetBackend(dataset_path)
    return LeRobot365DatasetBackend(dataset_path)


class BaseDatasetBackend(ABC):
    format: str

    @abstractmethod
    def get_env_meta(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    def list_demo_ids(self) -> List[str]:
        ...

    @abstractmethod
    def list_demo_records(self) -> List[DemoRecord]:
        ...

    @abstractmethod
    def load_scene_payload(self, demo_id: str) -> Dict[str, Any]:
        """Return ep_meta, ep_meta_raw, model_xml (optional), layout/style, fixture_refs."""

    @abstractmethod
    def read_demo_arrays(self, demo_id: str) -> Tuple[np.ndarray, np.ndarray]:
        ...


class Hdf5DatasetBackend(BaseDatasetBackend):
    format = "hdf5"

    def __init__(self, dataset_path: str | Path):
        import h5py  # lazy: optional when only LeRobot365 is used

        self._h5py = h5py
        self.path = Path(os.path.expanduser(str(dataset_path))).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

    def get_env_meta(self) -> Dict[str, Any]:
        with self._h5py.File(self.path, "r") as f:
            return json.loads(_decode(f["data"].attrs["env_args"]))

    def list_demo_ids(self) -> List[str]:
        with self._h5py.File(self.path, "r") as f:
            return sorted(f["data"].keys(), key=_demo_sort_key)

    def list_demo_records(self) -> List[DemoRecord]:
        records: List[DemoRecord] = []
        with self._h5py.File(self.path, "r") as f:
            for demo_id in self.list_demo_ids():
                grp = f["data"][demo_id]
                ep_meta = json.loads(_decode(grp.attrs.get("ep_meta", "{}")))
                fixture_refs = ep_meta.get("fixture_refs", {}) or {}
                records.append(
                    DemoRecord(
                        demo_id=demo_id,
                        episode_index=_demo_index(demo_id),
                        layout_id=ep_meta.get("layout_id"),
                        style_id=ep_meta.get("style_id"),
                        lang=str(ep_meta.get("lang", "")),
                        target_fixture=fixture_refs.get("target_fixture"),
                        length=int(grp["actions"].shape[0]),
                    )
                )
        return records

    def load_scene_payload(self, demo_id: str) -> Dict[str, Any]:
        with self._h5py.File(self.path, "r") as f:
            grp = f["data"][demo_id]
            ep_meta_raw = _decode(grp.attrs.get("ep_meta", "{}"))
            ep_meta = json.loads(ep_meta_raw)
            model_xml = _decode(grp.attrs.get("model_file", None))
            return {
                "demo_id": demo_id,
                "ep_meta": ep_meta,
                "ep_meta_raw": ep_meta_raw,
                "model_xml": model_xml,
                "layout_id": ep_meta.get("layout_id"),
                "style_id": ep_meta.get("style_id"),
                "fixture_refs": ep_meta.get("fixture_refs", {}),
            }

    def read_demo_arrays(self, demo_id: str) -> Tuple[np.ndarray, np.ndarray]:
        with self._h5py.File(self.path, "r") as f:
            grp = f["data"][demo_id]
            return np.asarray(grp["states"][:]), np.asarray(grp["actions"][:])


class LeRobot365DatasetBackend(BaseDatasetBackend):
    format = "lerobot365"

    def __init__(self, dataset_path: str | Path):
        self.source_path = Path(os.path.expanduser(str(dataset_path))).resolve()
        self.root = resolve_lerobot_root(self.source_path)
        self._info = json.loads((self.root / "meta" / "info.json").read_text(encoding="utf-8"))
        meta_path = self.root / "extras" / "dataset_meta.json"
        if meta_path.is_file():
            self._dataset_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            self._dataset_meta = {}
        self._episodes = self._load_episodes_jsonl()
        self._tasks = self._load_tasks_jsonl()
        self._chunk_size = int(self._info.get("chunks_size", 1000))

    def _load_episodes_jsonl(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        path = self.root / "meta" / "episodes.jsonl"
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def _load_tasks_jsonl(self) -> Dict[int, str]:
        tasks: Dict[int, str] = {}
        path = self.root / "meta" / "tasks.jsonl"
        if not path.is_file():
            return tasks
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                tasks[int(row["task_index"])] = str(row["task"])
        return tasks

    def _episode_dir(self, episode_index: int) -> Path:
        return self.root / "extras" / f"episode_{episode_index:06d}"

    def _parquet_path(self, episode_index: int) -> Path:
        chunk = episode_index // self._chunk_size
        template = str(self._info.get("data_path", "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet"))
        rel = template.format(episode_chunk=chunk, episode_index=episode_index)
        return self.root / rel

    def get_env_meta(self) -> Dict[str, Any]:
        env_args = self._dataset_meta.get("env_args")
        if isinstance(env_args, dict) and "env_name" in env_args:
            return env_args
        raise ValueError(f"env_args missing in {self.root / 'extras/dataset_meta.json'}")

    def list_demo_ids(self) -> List[str]:
        return [f"episode_{int(row['episode_index']):06d}" for row in self._episodes]

    def list_demo_records(self) -> List[DemoRecord]:
        records: List[DemoRecord] = []
        for row in self._episodes:
            ep_idx = int(row["episode_index"])
            demo_id = f"episode_{ep_idx:06d}"
            payload = self.load_scene_payload(demo_id)
            ep_meta = payload["ep_meta"]
            fixture_refs = ep_meta.get("fixture_refs", {}) or {}
            tasks = row.get("tasks") or []
            lang = str(tasks[0]) if tasks else str(ep_meta.get("lang", ""))
            records.append(
                DemoRecord(
                    demo_id=demo_id,
                    episode_index=ep_idx,
                    layout_id=ep_meta.get("layout_id"),
                    style_id=ep_meta.get("style_id"),
                    lang=lang,
                    target_fixture=fixture_refs.get("target_fixture"),
                    length=int(row.get("length", 0)),
                )
            )
        return records

    def load_scene_payload(self, demo_id: str) -> Dict[str, Any]:
        ep_idx = _demo_index(demo_id)
        ep_dir = self._episode_dir(ep_idx)
        ep_meta_path = ep_dir / "ep_meta.json"
        if not ep_meta_path.is_file():
            raise FileNotFoundError(ep_meta_path)
        ep_meta = json.loads(ep_meta_path.read_text(encoding="utf-8"))
        ep_meta_raw = json.dumps(ep_meta, ensure_ascii=False)
        model_xml = None
        model_gz = ep_dir / "model.xml.gz"
        if model_gz.is_file():
            with gzip.open(model_gz, "rt", encoding="utf-8") as f:
                model_xml = f.read()
        return {
            "demo_id": demo_id,
            "ep_meta": ep_meta,
            "ep_meta_raw": ep_meta_raw,
            "model_xml": model_xml,
            "layout_id": ep_meta.get("layout_id"),
            "style_id": ep_meta.get("style_id"),
            "fixture_refs": ep_meta.get("fixture_refs", {}),
        }

    def read_demo_arrays(self, demo_id: str) -> Tuple[np.ndarray, np.ndarray]:
        ep_idx = _demo_index(demo_id)
        states_path = self._episode_dir(ep_idx) / "states.npz"
        if not states_path.is_file():
            raise FileNotFoundError(states_path)
        states = np.asarray(np.load(states_path)["states"])

        parquet_path = self._parquet_path(ep_idx)
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("pandas is required for LeRobot365 datasets") from exc
        if not parquet_path.is_file():
            raise FileNotFoundError(parquet_path)
        df = pd.read_parquet(parquet_path)
        actions = np.asarray(df["action"].tolist(), dtype=np.float32)
        return states, actions


def _demo_sort_key(name: str):
    if name.startswith("demo_"):
        suffix = name.split("demo_", 1)[1]
        if suffix.isdigit():
            return (0, int(suffix))
    if name.startswith("episode_"):
        suffix = name.split("episode_", 1)[1]
        if suffix.isdigit():
            return (0, int(suffix))
    return (1, name)


def _demo_index(demo_id: str) -> int:
    if demo_id.startswith("demo_"):
        return int(demo_id.split("demo_", 1)[1])
    if demo_id.startswith("episode_"):
        return int(demo_id.split("episode_", 1)[1])
    raise ValueError(f"Unknown demo id format: {demo_id}")
