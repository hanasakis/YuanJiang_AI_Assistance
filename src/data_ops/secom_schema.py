"""SECOM dataset schema and parser.

Parses the raw SECOM text files and converts them into structured pandas
DataFrames with consistent column naming and label encoding.

SECOM data format:
  - secom.data:   1567 lines, space-separated floats, NaN as "NaN"
  - secom_labels.data: 1567 lines, -1 (pass) or 1 (fail)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# SECOM has 590 anonymized sensor features
_FEATURE_COUNT = 590
_FEATURE_COLUMNS = [f"feature_{i:03d}" for i in range(1, _FEATURE_COUNT + 1)]

# Label encoding: SECOM uses -1=pass, 1=fail.
# We normalize to 0=pass, 1=fail for clarity.
_LABEL_MAP = {-1: 0, 1: 1}
_LABEL_NAME_MAP = {0: "pass", 1: "fail"}


def load_secom_data(raw_dir: str | Path = "data/raw") -> pd.DataFrame:
    """Load secom.data into a DataFrame with named feature columns.

    Args:
        raw_dir: Path to directory containing secom.data.

    Returns:
        DataFrame with columns: sample_id, feature_001..feature_590.
        All feature values are float64. NaN where sensor was inactive.

    Raises:
        FileNotFoundError: If secom.data does not exist in raw_dir.
    """
    raw_dir = Path(raw_dir)
    data_path = raw_dir / "secom.data"

    if not data_path.exists():
        raise FileNotFoundError(
            f"{data_path} not found. "
            f"Download from https://archive.ics.uci.edu/dataset/179/secom "
            f"and place in {raw_dir}/"
        )

    df = pd.read_csv(
        data_path,
        sep=r"\s+",
        header=None,
        na_values=["NaN", "nan", ""],
        dtype="float64",
    )

    # The dataset should have 590 columns
    actual_cols = df.shape[1]
    if actual_cols != _FEATURE_COUNT:
        raise ValueError(
            f"Expected {_FEATURE_COUNT} feature columns, "
            f"found {actual_cols}. File may be misformatted."
        )

    df.columns = _FEATURE_COLUMNS
    df.insert(0, "sample_id", range(1, len(df) + 1))

    return df


def load_secom_labels(raw_dir: str | Path = "data/raw") -> pd.DataFrame:
    """Load secom_labels.data into a DataFrame with normalized labels.

    Args:
        raw_dir: Path to directory containing secom_labels.data.

    Returns:
        DataFrame with columns: sample_id, label, label_name.
        label: 0 (pass) or 1 (fail).
        label_name: "pass" or "fail".

    Raises:
        FileNotFoundError: If secom_labels.data does not exist.
    """
    raw_dir = Path(raw_dir)
    labels_path = raw_dir / "secom_labels.data"

    if not labels_path.exists():
        raise FileNotFoundError(
            f"{labels_path} not found. "
            f"Download from https://archive.ics.uci.edu/dataset/179/secom "
            f"and place in {raw_dir}/"
        )

    df = pd.read_csv(
        labels_path,
        sep=r"\s+",
        header=None,
        names=["raw_label"],
    )

    df.insert(0, "sample_id", range(1, len(df) + 1))
    df["label"] = df["raw_label"].map(_LABEL_MAP)
    df["label_name"] = df["label"].map(_LABEL_NAME_MAP)

    # Validate: all rows mapped successfully
    if df["label"].isna().any():
        bad = df[df["label"].isna()]["raw_label"].unique().tolist()
        raise ValueError(
            f"Unexpected label values found: {bad}. "
            f"Expected only -1 (pass) and 1 (fail)."
        )

    df["label"] = df["label"].astype("int8")
    return df


def compute_feature_missingness(measurements: pd.DataFrame) -> pd.DataFrame:
    """Compute per-feature missing value statistics.

    Args:
        measurements: DataFrame from load_secom_data().

    Returns:
        DataFrame with columns: feature_name, total_samples, missing_count,
        missing_rate.
    """
    rows: list[dict] = []
    total = len(measurements)

    for col in _FEATURE_COLUMNS:
        missing = int(measurements[col].isna().sum())
        rows.append({
            "feature_name": col,
            "total_samples": total,
            "missing_count": missing,
            "missing_rate": round(missing / total, 6),
        })

    return pd.DataFrame(rows)


def compute_feature_stats(measurements: pd.DataFrame) -> pd.DataFrame:
    """Compute per-feature distribution statistics (ignoring NaN).

    Args:
        measurements: DataFrame from load_secom_data().

    Returns:
        DataFrame with columns: feature_name, mean, std, min, p25, median,
        p75, max.
    """
    import numpy as np

    rows: list[dict] = []

    def _safe(val) -> float | None:
        """Convert describe() output to float, returning None for NaN."""
        if val is None:
            return None
        f = float(val)
        return None if np.isnan(f) else round(f, 6)

    for col in _FEATURE_COLUMNS:
        series = measurements[col].dropna()
        if len(series) == 0:
            rows.append({
                "feature_name": col,
                "mean": None, "std": None,
                "min": None, "p25": None,
                "median": None, "p75": None, "max": None,
            })
        else:
            desc = series.describe()
            rows.append({
                "feature_name": col,
                "mean": _safe(desc["mean"]),
                "std": _safe(desc["std"]),
                "min": _safe(desc["min"]),
                "p25": _safe(desc["25%"]),
                "median": _safe(desc["50%"]),
                "p75": _safe(desc["75%"]),
                "max": _safe(desc["max"]),
            })

    return pd.DataFrame(rows)


def get_schema_info() -> dict:
    """Return metadata about the SECOM schema."""
    return {
        "feature_count": _FEATURE_COUNT,
        "feature_columns": _FEATURE_COLUMNS,
        "label_map": {"raw": _LABEL_MAP, "names": _LABEL_NAME_MAP},
        "expected_rows": 1567,
        "expected_labels": {"pass": 1463, "fail": 104},
    }
