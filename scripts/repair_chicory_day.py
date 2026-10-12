#!/usr/bin/env python3
"""Repair anti-chicory copy on one content file.

Use this after a generate slot has already saved output/content_<date>.json
and that day's featured jar contains chicory. The script rewrites attack
lines (roasted root filler, never drink roasted root, chicory-as-poison)
into an honest 70% coffee / 30% chicory disclosure.

It does not publish. It does not run the morning or evening slots.
Pass --write to update the JSON. The default is a dry run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# `python scripts/repair_chicory_day.py` puts scripts/ on sys.path, not the repo
# root. Same bootstrap as the other repo-root entry points (tests, verify_refactor).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _joined_copy(node) -> str:
    from content_generator.core.product_truth import piece_copy_text

    parts: list[str] = []

    def walk(value) -> None:
        if isinstance(value, dict):
            text = piece_copy_text(value)
            if text:
                parts.append(text)
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return "\n".join(parts)


def remaining_findings(content: dict) -> list[dict]:
    from content_generator.core.product_truth import featured_product_name, product_truth_findings

    featured = featured_product_name(content)
    return product_truth_findings(_joined_copy(content), featured=featured)


def repair_file(path: Path, *, write: bool) -> int:
    from content_generator.core.product_truth import repair_content

    if not path.is_file():
        print(f"missing content file: {path}", file=sys.stderr)
        print("Generate must already have saved this date. This script does not publish.", file=sys.stderr)
        return 2
    original = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(original, dict):
        print(f"{path} is not a content object", file=sys.stderr)
        return 2
    repaired = repair_content(original)
    findings = remaining_findings(repaired)
    if findings:
        print(f"repair left {len(findings)} product-truth failure(s); file not written", file=sys.stderr)
        for item in findings[:8]:
            print(f"- {item.get('reason')}: {item.get('claim')}", file=sys.stderr)
        return 1
    before = json.dumps(original, ensure_ascii=False, sort_keys=True)
    after = json.dumps(repaired, ensure_ascii=False, sort_keys=True)
    changed = before != after
    print(f"{path}: {'updated' if changed else 'already clean'}; product-truth clear; not published")
    if write:
        path.write_text(json.dumps(repaired, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        print("dry run — pass --write to save the repaired JSON")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="2026-10-12", help="IST content date, YYYY-MM-DD")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--write", action="store_true", help="Save the repaired JSON. Still does not publish.")
    parser.add_argument("--dry-run", action="store_true", help="Report only. This is the default.")
    args = parser.parse_args(argv)
    path = Path(args.output_dir) / f"content_{args.date}.json"
    return repair_file(path, write=bool(args.write) and not args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
