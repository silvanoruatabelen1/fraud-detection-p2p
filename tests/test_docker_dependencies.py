import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_replayer_image_installs_its_runtime_dependencies() -> None:
    dockerfile = (ROOT / "docker" / "replayer.Dockerfile").read_text()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert "--no-default-groups --group replayer" in dockerfile
    assert set(project["dependency-groups"]["replayer"]) >= {
        "pandas>=2.2",
        "pyarrow>=17",
        "requests>=2.32",
    }
