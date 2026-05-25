"""Guided download for SECOM dataset from UCI Machine Learning Repository.

This module does NOT auto-download — it tells the user exactly what to do
and verifies the result. Auto-download from UCI is unreliable because their
server configuration changes periodically.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

_RAW = Path("data/raw")
_EXPECTED_FILES = ("secom.data", "secom_labels.data")
_UCI_URL = "https://archive.ics.uci.edu/dataset/179/secom"
_UCI_DOWNLOAD_URL = "https://archive.ics.uci.edu/static/public/179/secom.zip"


def check_data_exists() -> dict[str, bool]:
    """Check which SECOM files are present in data/raw/.

    Returns:
        Dict mapping filename → exists (True/False).
    """
    return {f: (_RAW / f).exists() for f in _EXPECTED_FILES}


def print_download_instructions() -> None:
    """Print step-by-step download instructions for the user."""
    status = check_data_exists()
    missing = [f for f, exists in status.items() if not exists]

    if not missing:
        print("[OK] All SECOM data files present in data/raw/.")
        return

    print("=" * 60)
    print("  SECOM dataset files missing:")
    for f in missing:
        print(f"    - {f}")
    print()
    print("  Download options:")
    print()
    print(f"  1. Browser: {_UCI_URL}")
    print(f"  2. Direct:  {_UCI_DOWNLOAD_URL}")
    print()
    print("  Steps:")
    print("    1. Download secom.zip")
    print("    2. Unzip into data/raw/")
    print("    3. Verify: data/raw/secom.data")
    print("               data/raw/secom_labels.data")
    print("    4. Re-run this script")
    print("=" * 60)


def verify_files() -> dict[str, str | None]:
    """Verify integrity of downloaded SECOM files.

    Returns:
        Dict mapping filename → None (OK) or error message.
    """
    results: dict[str, str | None] = {}

    for filename in _EXPECTED_FILES:
        path = _RAW / filename
        if not path.exists():
            results[filename] = "File not found"
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            results[filename] = f"Read error: {exc}"
            continue

        if not content.strip():
            results[filename] = "File is empty"
            continue

        # secom.data: should have 1567 lines, space-separated numbers
        # secom_labels.data: should have 1567 lines, each -1 or 1
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        if filename == "secom.data":
            if len(lines) != 1567:
                results[filename] = (
                    f"Expected 1567 rows, got {len(lines)}. "
                    f"File may be truncated or corrupted."
                )
            else:
                results[filename] = None
        elif filename == "secom_labels.data":
            if len(lines) != 1567:
                results[filename] = (
                    f"Expected 1567 rows, got {len(lines)}. "
                    f"File may be truncated or corrupted."
                )
            else:
                results[filename] = None

    return results


if __name__ == "__main__":
    print_download_instructions()
    results = verify_files()
    for fname, err in results.items():
        if err:
            print(f"[FAIL] {fname}: {err}")
        else:
            print(f"[OK] {fname}")
