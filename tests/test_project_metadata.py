from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _project_metadata() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


def test_pypi_project_metadata_is_complete() -> None:
    project = _project_metadata()

    assert project["requires-python"] == ">=3.11"
    assert project["urls"] == {
        "Homepage": "https://nexus.oktolabs.ai",
        "Documentation": "https://github.com/OktoLabsAI/okto-nexus#readme",
        "Repository": "https://github.com/OktoLabsAI/okto-nexus",
        "Issues": "https://github.com/OktoLabsAI/okto-nexus/issues",
    }
    assert all(url.startswith("https://") for url in project["urls"].values())

    assert {
        "mcp",
        "model-context-protocol",
        "multi-agent",
        "agent-coordination",
        "local-first",
        "developer-tools",
    } <= set(project["keywords"])

    classifiers = set(project["classifiers"])
    assert "Development Status :: 3 - Alpha" in classifiers
    assert "Intended Audience :: Developers" in classifiers
    for version in ("3.11", "3.12", "3.13"):
        assert f"Programming Language :: Python :: {version}" in classifiers
