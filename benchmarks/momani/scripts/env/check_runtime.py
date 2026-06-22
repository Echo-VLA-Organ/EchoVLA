#!/usr/bin/env python3

import argparse
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


NAVGEN_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = str(NAVGEN_ROOT / "config/runtime/runtime_manifest.yaml")


def _load_yaml(path: str) -> Dict[str, Any]:
    try:
        import yaml
    except Exception as exc:
        raise RuntimeError("missing PyYAML, cannot load runtime manifest") from exc

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"manifest not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("runtime manifest must be a YAML object")
    return data


def _check_python(
    runtime_cfg: Dict[str, Any], strict_executable: bool, results: Dict[str, Any]
) -> None:
    expected_exec = str(runtime_cfg.get("python_executable", "")).strip()
    expected_major_minor = str(runtime_cfg.get("python_major_minor", "")).strip()
    actual_exec = str(Path(sys.executable).resolve())
    actual_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"

    pass_exec = True
    if strict_executable and expected_exec:
        pass_exec = actual_exec == str(Path(expected_exec).resolve())

    pass_pyver = True
    if expected_major_minor:
        pass_pyver = actual_major_minor == expected_major_minor

    results["python"] = {
        "expected_executable": expected_exec,
        "actual_executable": actual_exec,
        "strict_executable": bool(strict_executable),
        "pass_executable": bool(pass_exec),
        "expected_major_minor": expected_major_minor,
        "actual_major_minor": actual_major_minor,
        "pass_major_minor": bool(pass_pyver),
    }


def _check_platform(runtime_cfg: Dict[str, Any], results: Dict[str, Any]) -> None:
    supported = [str(x).lower() for x in runtime_cfg.get("supported_platforms", [])]
    actual = str(platform.system()).lower()
    if not supported:
        ok = True
    else:
        ok = actual in supported
    results["platform"] = {
        "supported": supported,
        "actual": actual,
        "pass": bool(ok),
    }


def _check_packages(packages_cfg: Dict[str, Any], results: Dict[str, Any]) -> None:
    rows: List[Dict[str, Any]] = []
    for pkg_name, expected_ver in packages_cfg.items():
        expected = str(expected_ver)
        try:
            actual = importlib.metadata.version(str(pkg_name))
            ok = actual == expected
        except Exception:
            actual = None
            ok = False
        rows.append(
            {
                "package": str(pkg_name),
                "expected": expected,
                "actual": actual,
                "pass": bool(ok),
            }
        )
    results["packages"] = rows


def _normalize_git_url(url: Optional[str]) -> Optional[str]:
    if url is None:
        return None
    s = str(url).strip()
    if not s:
        return None
    if s.endswith(".git"):
        s = s[:-4]
    return s.rstrip("/")


def _read_direct_url(distribution_name: str) -> Dict[str, Any]:
    try:
        dist = importlib.metadata.distribution(distribution_name)
    except Exception:
        return {}
    files = list(dist.files or [])
    rel = None
    for f in files:
        if str(f).endswith("direct_url.json"):
            rel = f
            break
    if rel is None:
        return {}
    p = dist.locate_file(rel)
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _check_sources(sources_cfg: Dict[str, Any], results: Dict[str, Any]) -> None:
    rows: List[Dict[str, Any]] = []
    for source_name, source_cfg_any in sources_cfg.items():
        source_cfg = dict(source_cfg_any or {})
        package_name = str(source_cfg.get("package", source_name))
        expected_url = _normalize_git_url(source_cfg.get("git_url"))
        expected_ref = str(source_cfg.get("git_ref", "")).strip()
        allow_local = bool(source_cfg.get("allow_local_editable", True))

        try:
            importlib.metadata.distribution(package_name)
            import_ok = True
        except Exception:
            import_ok = False
        module_file = None

        direct_url = _read_direct_url(package_name)
        actual_url = direct_url.get("url")
        actual_ref = None
        if isinstance(direct_url.get("vcs_info"), dict):
            actual_ref = direct_url.get("vcs_info", {}).get("commit_id")

        normalized_actual = _normalize_git_url(actual_url)
        is_local_editable = bool(actual_url and str(actual_url).startswith("file://"))

        if is_local_editable:
            pass_url = bool(allow_local)
            pass_ref = bool(allow_local)
        else:
            if expected_url is None:
                pass_url = True
            else:
                pass_url = normalized_actual == expected_url

            if not expected_ref:
                pass_ref = True
            else:
                pass_ref = bool(actual_ref and str(actual_ref).startswith(expected_ref))

        row_pass = bool(import_ok and pass_url and pass_ref)

        rows.append(
            {
                "source": str(source_name),
                "package": package_name,
                "expected_git_url": expected_url,
                "expected_git_ref": expected_ref,
                "allow_local_editable": allow_local,
                "actual_url": actual_url,
                "actual_git_ref": actual_ref,
                "module_file": module_file,
                "pass_import": bool(import_ok),
                "pass_url": bool(pass_url),
                "pass_ref": bool(pass_ref),
                "pass": row_pass,
            }
        )

    results["sources"] = rows


def check_runtime(manifest_path: str, strict_executable: bool) -> Dict[str, Any]:
    manifest = _load_yaml(manifest_path)
    runtime_cfg = dict(manifest.get("runtime", {}))
    packages_cfg = dict(manifest.get("packages", {}))
    sources_cfg = dict(manifest.get("sources", {}))

    results: Dict[str, Any] = {
        "manifest": str(manifest_path),
        "runtime_name": str(runtime_cfg.get("name", "unknown")),
    }

    _check_python(runtime_cfg, strict_executable=strict_executable, results=results)
    _check_platform(runtime_cfg, results=results)
    _check_packages(packages_cfg, results=results)
    _check_sources(sources_cfg, results=results)

    pkg_pass = all(bool(r["pass"]) for r in results["packages"])
    src_pass = all(bool(r["pass"]) for r in results["sources"])
    py = results["python"]
    py_pass = bool(py["pass_major_minor"]) and bool(py["pass_executable"])
    platform_pass = bool(results["platform"]["pass"])
    results["pass"] = bool(pkg_pass and src_pass and py_pass and platform_pass)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Check navgen runtime consistency")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--strict-executable", action="store_true")
    parser.add_argument("--json-output", default=None)
    args = parser.parse_args()

    results = check_runtime(
        manifest_path=args.manifest,
        strict_executable=bool(args.strict_executable),
    )

    if args.json_output:
        out = Path(args.json_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(results, ensure_ascii=True, indent=2), encoding="utf-8"
        )

    print(f"[runtime_check] manifest: {args.manifest}")
    print(f"[runtime_check] pass: {results['pass']}")
    print(
        f"[runtime_check] platform: actual={results['platform']['actual']} supported={results['platform']['supported']} pass={results['platform']['pass']}"
    )
    for row in results["packages"]:
        print(
            f"[runtime_check] pkg {row['package']}: expected={row['expected']} actual={row['actual']} pass={row['pass']}"
        )
    for row in results["sources"]:
        print(
            f"[runtime_check] source {row['source']}: expected_url={row['expected_git_url']} actual_url={row['actual_url']} pass={row['pass']}"
        )

    if not results["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
