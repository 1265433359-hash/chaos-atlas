from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / 'src'))
from chaosatlas.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
