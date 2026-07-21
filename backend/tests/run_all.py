from __future__ import annotations

from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for test_file in sorted(Path(__file__).parent.glob("test_*.py")):
    runpy.run_path(str(test_file), run_name="__main__")
