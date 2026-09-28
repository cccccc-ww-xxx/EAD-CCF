"""Load the central configuration file (config/config.yaml)."""

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


def load_config(path: Path | str = CONFIG_PATH) -> dict:
    """Read the YAML config and return it as a plain dictionary."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def paths() -> dict:
    """Standard project folders, created if missing."""
    p = {
        "root": PROJECT_ROOT,
        "raw": PROJECT_ROOT / "data" / "raw",
        "derived": PROJECT_ROOT / "data" / "derived",
        "out_py": PROJECT_ROOT / "outputs" / "python",
        "out_sas": PROJECT_ROOT / "outputs" / "sas",
        "figures": PROJECT_ROOT / "outputs" / "figures",
        "docs": PROJECT_ROOT / "docs",
    }
    for key in ("raw", "derived", "out_py", "figures", "docs"):
        p[key].mkdir(parents=True, exist_ok=True)
    return p
