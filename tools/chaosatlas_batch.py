from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from chaosatlas.cli import main

# The product snapshot keeps the historical live batch implementation under
# ``_legacy_chaosatlas_batch.py`` during migration.  Re-export its public
# entry point so the compatibility CLI and direct Python callers share one
# implementation.
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
    from tools import _legacy_chaosatlas_batch

    value = getattr(_legacy_chaosatlas_batch, name)
    globals()[name] = value
    return value

if __name__ == '__main__':
    raise SystemExit(main())
