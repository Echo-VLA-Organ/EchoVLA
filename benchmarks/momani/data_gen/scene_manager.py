import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import robosuite

import robocasa  # noqa: F401

from utils.dataset_backend import BaseDatasetBackend, open_dataset_backend


@dataclass
class SceneSpec:
    demo_id: str
    ep_meta: Dict[str, Any]
    ep_meta_raw: str
    model_xml: Optional[str]
    layout_id: Optional[int]
    style_id: Optional[int]
    fixture_refs: Dict[str, Any]


def get_env_meta_from_dataset(dataset_path: str) -> Dict[str, Any]:
    backend = open_dataset_backend(dataset_path)
    return backend.get_env_meta()


def _reset_to(env, state: Dict[str, Any]):
    if "model" in state:
        ep_meta = json.loads(state.get("ep_meta", "{}"))
        if hasattr(env, "set_attrs_from_ep_meta"):
            env.set_attrs_from_ep_meta(ep_meta)
        elif hasattr(env, "set_ep_meta"):
            env.set_ep_meta(ep_meta)

        env.reset()
        robosuite_version_id = int(robosuite.__version__.split(".")[1])
        if robosuite_version_id <= 3:
            from robosuite.utils.mjcf_utils import postprocess_model_xml

            xml = postprocess_model_xml(state["model"])
        else:
            xml = env.edit_model_xml(state["model"])

        env.reset_from_xml_string(xml)
        env.sim.reset()

    if "states" in state:
        env.sim.set_state_from_flattened(state["states"])
        env.sim.forward()

    if hasattr(env, "update_sites"):
        env.update_sites()
    if hasattr(env, "update_state"):
        env.update_state()


class SceneManager:
    """Load scenes from HDF5 or RoboCasa365 LeRobot datasets."""

    def __init__(self, dataset_path: str):
        self.dataset_path = os.path.expanduser(dataset_path)
        self.backend: BaseDatasetBackend = open_dataset_backend(self.dataset_path)

    @property
    def dataset_format(self) -> str:
        return self.backend.format

    def list_demo_ids(self):
        return self.backend.list_demo_ids()

    def load_scene_spec(self, demo_id: str) -> SceneSpec:
        payload = self.backend.load_scene_payload(demo_id)
        return SceneSpec(
            demo_id=demo_id,
            ep_meta=payload["ep_meta"],
            ep_meta_raw=payload["ep_meta_raw"],
            model_xml=payload.get("model_xml"),
            layout_id=payload.get("layout_id"),
            style_id=payload.get("style_id"),
            fixture_refs=payload.get("fixture_refs", {}),
        )

    def build_env(self, force_offscreen: bool = False):
        env_meta = self.backend.get_env_meta()
        env_kwargs = dict(env_meta["env_kwargs"])
        env_kwargs["env_name"] = env_meta["env_name"]
        env_kwargs["has_renderer"] = False
        env_kwargs["has_offscreen_renderer"] = bool(force_offscreen)
        env_kwargs["use_camera_obs"] = False
        env_kwargs["renderer"] = "mjviewer"
        return robosuite.make(**env_kwargs)

    def reset_env_to_demo_scene(
        self, env, demo_id: str, initial_state=None
    ) -> SceneSpec:
        spec = self.load_scene_spec(demo_id)
        state = {"ep_meta": spec.ep_meta_raw}
        if spec.model_xml is not None:
            state["model"] = spec.model_xml
        if initial_state is not None:
            state["states"] = initial_state
        _reset_to(env, state)
        return spec

    def read_demo_arrays(self, demo_id: str) -> Tuple[Any, Any]:
        return self.backend.read_demo_arrays(demo_id)
