"""Docs tooling test: generated root artifacts must match their canonical docs."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_materialized_files_are_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "materialize_docs.py"), "--check"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
