from pathlib import Path
from typing import Any


def read_yaml(path_to_yaml: Path) -> dict[str, Any]:
    """Read a YAML file and return its content as a plain dictionary."""

    import yaml

    with path_to_yaml.open(encoding="utf-8") as yaml_file:
        content = yaml.safe_load(yaml_file)
    return content or {}
