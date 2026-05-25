"""Guided download for Olist Brazilian E-Commerce dataset from Kaggle.

This module does NOT auto-download — it tells the user how to obtain the
dataset and verifies the result. Kaggle credentials are the user's
responsibility; we never hardcode or store API tokens.
"""
from __future__ import annotations

from pathlib import Path

_RAW = Path("data/raw")
_KAGGLE_SLUG = "olistbr/brazilian-ecommerce"
_KAGGLE_URL = f"https://www.kaggle.com/datasets/{_KAGGLE_SLUG}"

_EXPECTED_FILES = (
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "product_category_name_translation.csv",
)


def check_data_exists() -> dict[str, bool]:
    """Check which Olist CSV files are present in data/raw/.

    Returns:
        Dict mapping filename -> exists (True/False).
    """
    return {f: (_RAW / f).exists() for f in _EXPECTED_FILES}


def print_download_instructions() -> None:
    """Print step-by-step instructions for obtaining the Olist dataset."""
    status = check_data_exists()
    missing = [f for f, exists in status.items() if not exists]

    if not missing:
        print("[OK] All 9 Olist CSV files present in data/raw/.")
        return

    print("=" * 60)
    print("  Olist dataset files missing:")
    for f in missing:
        print(f"    - {f}")
    print()
    print("  Download options:")
    print()
    print(f"  1. Kaggle page: {_KAGGLE_URL}")
    print(f"  2. Kaggle CLI:  kaggle datasets download {_KAGGLE_SLUG}")
    print(f"                    -p data/raw/ --unzip")
    print()
    print("  Steps:")
    print("    a. Install Kaggle CLI: pip install kaggle")
    print("    b. Place kaggle.json in ~/.kaggle/ (from Kaggle account)")
    print("    c. Run the CLI command above")
    print("    d. Verify: ls data/raw/olist_*.csv")
    print("    e. Re-run this script to confirm")
    print()
    print("  NOTE: Do NOT commit data/raw/ to Git (it is .gitignored).")
    print("=" * 60)


def verify_files() -> dict[str, str | None]:
    """Verify integrity of downloaded Olist files.

    Returns:
        Dict mapping filename -> None (OK) or error message.
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

        # Verify it's a valid CSV with a header row
        lines = [ln for ln in content.splitlines() if ln.strip()]
        if len(lines) < 2:
            results[filename] = (
                "CSV has fewer than 2 lines (header + data expected)"
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
            print(f"[OK]  {fname}")
