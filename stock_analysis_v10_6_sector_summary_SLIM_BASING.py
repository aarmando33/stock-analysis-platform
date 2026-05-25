"""Compatibility entry point for the canonical script under scripts/."""

from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    scripts_dir = Path(__file__).parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    runpy.run_path(
        str(scripts_dir / "stock_analysis_v10_6_sector_summary_SLIM_BASING.py"),
        run_name="__main__",
    )
