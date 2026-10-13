"""Docs tooling test: generated root artifacts must match their canonical docs."""
from __future__ import annotations

import importlib.util
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


def test_brand_and_design_are_split_from_the_dsd() -> None:
    spec = importlib.util.spec_from_file_location("materialize_docs", ROOT / "tools" / "materialize_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = module.targets(ROOT)

    brand, design = out["BRAND.md"], out["DESIGN.md"]
    assert "## 0. Brand Stance" in brand and "## 1. Design Philosophy" in brand
    assert "## 2. " not in brand
    assert "## 2. Brand Primitives" in design and "## 7. Quality Gate" in design
    assert "## 1. " not in design and "## 8. " not in design and "## 9. " not in design


def test_root_titles_use_the_brand_name() -> None:
    spec = importlib.util.spec_from_file_location("materialize_docs", ROOT / "tools" / "materialize_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = module.targets(ROOT)

    assert "\n# Brand: Silverbot\n" in out["BRAND.md"]
    assert "\n# Design System: Silverbot\n" in out["DESIGN.md"]
