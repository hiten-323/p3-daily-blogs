"""CI Guard: Ensure no NameError-prone leftover references to reel_2 or arch_2 exist in content_generator/."""
import ast
import os
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CG_DIR = ROOT / "content_generator"


def test_ci_guard_no_reel_2_or_arch_2_in_content_generator():
    """Scans all Python files in content_generator/ and fails if any active code references arch_2 or reel_2."""
    hits = []
    for root, _, files in os.walk(CG_DIR):
        for f in files:
            if f.endswith(".py"):
                path = pathlib.Path(root) / f
                src = path.read_text(encoding="utf-8")
                tree = ast.parse(src, filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name) and node.id in ("arch_2", "reel_2"):
                        hits.append((str(path.relative_to(ROOT)), node.lineno, node.id))

    assert hits == [], f"Found NameError-prone leftover references to retired reel_2/arch_2: {hits}"
