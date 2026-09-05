from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from chaosatlas.cli import main

# Re-export the unified package implementation for compatibility with existing
# scripts that still import ``tools.chaosatlas_batch``.
_LEGACY_EXPORTS = {
    "append_batch_state",
    "append_policy_record",
    "build_batch_manifest",
    "build_live_batch_plan",
    "enrich_batch_result_from_artifacts",
    "run_live_batch",
    "summarize_batch_results",
    "validate_batch_resume",
}


def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from chaosatlas.orchestration import batch

    value = getattr(batch, name)
    globals()[name] = value
    return value

if __name__ == '__main__':
    raise SystemExit(main())
