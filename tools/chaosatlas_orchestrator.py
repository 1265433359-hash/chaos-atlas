"""Compatibility import for the unified ChaosAtlas RunEngine."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chaosatlas.orchestration.engine import PlanExecutor, RunDependencies, RunEngine, RunRequest, run_closed_loop

__all__ = ["PlanExecutor", "RunDependencies", "RunEngine", "RunRequest", "run_closed_loop"]
