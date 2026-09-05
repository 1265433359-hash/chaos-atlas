from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PRODUCT_DIRS = ("src", "cli", "projects", "docs", "scripts", "examples")
ROOT_FILES = ("README.md", "AGENTS.md", ".gitignore", "pyproject.toml", "pytest.ini")
COMPAT_WRAPPERS = ("chaosatlas.py", "run_closed_loop.py", "chaosatlas_batch.py")
PRODUCT_TESTS = ("test_repository_architecture.py",)
COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.py[cod]",
    "*.egg-info",
    "node_modules",
    ".git",
    ".pytest_cache",
    ".turbo",
    ".next",
)
EXCLUDED_TOOL_FILES = {"_legacy_chaosatlas.py", "_legacy_chaosatlas_batch.py"}


def build_snapshot(root: str | Path, destination: str | Path) -> Path:
    root_path = Path(root).resolve()
    destination_path = Path(destination).resolve()
    destination_path.mkdir(parents=True, exist_ok=True)
    if any(destination_path.iterdir()):
        raise ValueError(f"snapshot destination must be empty: {destination_path}")

    for directory in PRODUCT_DIRS:
        source = root_path / directory
        if source.exists():
            shutil.copytree(source, destination_path / directory, dirs_exist_ok=True, ignore=COPY_IGNORE)

    product_tests = root_path / "tests"
    legacy_tests = root_path / "tools" / "tests"
    tests_source = product_tests if (product_tests / PRODUCT_TESTS[0]).exists() else legacy_tests
    if tests_source.exists():
        tests_destination = destination_path / "tests"
        tests_destination.mkdir(parents=True, exist_ok=True)
        for test_name in PRODUCT_TESTS:
            source = tests_source / test_name
            if source.exists():
                shutil.copy2(source, tests_destination / test_name)
    fixtures_source = root_path / "tests" / "fixtures"
    if fixtures_source.exists():
        shutil.copytree(
            fixtures_source,
            destination_path / "tests" / "fixtures",
            dirs_exist_ok=True,
            ignore=COPY_IGNORE,
        )

    for name in ROOT_FILES:
        source = root_path / name
        if source.exists():
            shutil.copy2(source, destination_path / name)

    tools_destination = destination_path / "tools"
    tools_destination.mkdir(parents=True, exist_ok=True)
    tools_source = root_path / "tools"
    if tools_source.exists():
        for source in tools_source.rglob("*.py"):
            if "__pycache__" in source.parts or source.name in EXCLUDED_TOOL_FILES:
                continue
            relative = source.relative_to(tools_source)
            target = tools_destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    wrapper = (
        "from pathlib import Path\n"
        "import sys\n\n"
        "_ROOT = Path(__file__).resolve().parents[1]\n"
        "sys.path.insert(0, str(_ROOT))\n"
        "sys.path.insert(0, str(_ROOT / 'src'))\n"
        "from chaosatlas.cli import main\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )
    for name in COMPAT_WRAPPERS:
        (tools_destination / name).write_text(wrapper, encoding="utf-8")
    return destination_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a clean ChaosAtlas product snapshot.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    print(build_snapshot(args.root, args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
