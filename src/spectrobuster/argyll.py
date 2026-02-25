import os
import platform
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _platform_bin_candidates() -> list[Path]:
    root = _project_root()
    system = platform.system().lower()

    candidates: list[Path] = []
    if system == "darwin":
        candidates.extend(
            [
                root / "vendor" / "argyll" / "macos-arm64" / "bin",
                root / "vendor" / "argyll" / "macos" / "bin",
                root / "mac" / "Argyll_V3.5.0" / "bin",
            ]
        )
    elif system == "windows":
        candidates.extend(
            [
                root / "vendor" / "argyll" / "windows-x64" / "bin",
                root / "windows" / "Argyll_V3.5-2.0" / "bin",
            ]
        )

    return [path for path in candidates if path.exists()]


def build_argyll_env(base_env: dict | None = None) -> dict:
    env = dict(base_env) if base_env is not None else os.environ.copy()

    extra_paths = [str(path) for path in _platform_bin_candidates()]
    extra_paths.extend(["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", os.path.expanduser("~/bin")])

    existing = env.get("PATH", "")
    env["PATH"] = os.pathsep.join(extra_paths + [existing]) if existing else os.pathsep.join(extra_paths)
    return env


def resolve_spotread_command() -> str:
    executable_name = "spotread.exe" if platform.system().lower() == "windows" else "spotread"

    for directory in _platform_bin_candidates():
        candidate = directory / executable_name
        if candidate.exists():
            return str(candidate)

    return "spotread"
