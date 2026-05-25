"""Tests for src/data_ops/secom_schema.py — schema parsing and label encoding.

These tests use synthetic in-memory data and do NOT require the real
SECOM dataset files on disk.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.data_ops.secom_schema import (
    compute_feature_missingness,
    compute_feature_stats,
    get_schema_info,
    load_secom_data,
    load_secom_labels,
)


def _write_fake_secom_data(tmpdir: Path, n_rows: int = 100, n_cols: int = 10):
    """Write a minimal fake secom.data file for parser testing."""
    import numpy as np

    rng = np.random.default_rng(42)
    lines = []
    for _ in range(n_rows):
        values = []
        for _ in range(n_cols):
            if rng.random() < 0.1:  # 10% missing
                values.append("NaN")
            else:
                values.append(f"{rng.normal(0, 1):.6f}")
        lines.append("  ".join(values))
    (tmpdir / "secom.data").write_text("\n".join(lines))


def _write_fake_secom_labels(tmpdir: Path, n_rows: int = 100):
    """Write a minimal fake secom_labels.data file."""
    import numpy as np

    rng = np.random.default_rng(42)
    lines = [str(rng.choice([-1, 1])) for _ in range(n_rows)]
    (tmpdir / "secom_labels.data").write_text("\n".join(lines))


class TestLoadSecomData:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="secom.data"):
            load_secom_data("/nonexistent/path")

    def test_parses_fake_data(self, tmp_path):
        _write_fake_secom_data(tmp_path, n_rows=50, n_cols=5)
        # We need to override the feature count check.
        # secom_schema expects exactly 590 columns, so we test with
        # monkeypatch to validate the parser behavior on small data.
        import src.data_ops.secom_schema as mod

        original_count = mod._FEATURE_COUNT
        original_cols = mod._FEATURE_COLUMNS
        try:
            mod._FEATURE_COUNT = 5
            mod._FEATURE_COLUMNS = [f"feature_{i:03d}" for i in range(1, 6)]
            df = mod.load_secom_data(tmp_path)
            assert len(df) == 50
            assert list(df.columns[:2]) == ["sample_id", "feature_001"]
            assert df["sample_id"].iloc[0] == 1
            assert df["sample_id"].iloc[-1] == 50
        finally:
            mod._FEATURE_COUNT = original_count
            mod._FEATURE_COLUMNS = original_cols

    def test_sample_id_is_sequential(self, tmp_path):
        _write_fake_secom_data(tmp_path, n_rows=10, n_cols=5)
        import src.data_ops.secom_schema as mod

        original_count = mod._FEATURE_COUNT
        original_cols = mod._FEATURE_COLUMNS
        try:
            mod._FEATURE_COUNT = 5
            mod._FEATURE_COLUMNS = [f"feature_{i:03d}" for i in range(1, 6)]
            df = mod.load_secom_data(tmp_path)
            assert df["sample_id"].tolist() == list(range(1, 11))
        finally:
            mod._FEATURE_COUNT = original_count
            mod._FEATURE_COLUMNS = original_cols

    def test_column_count_mismatch_raises(self, tmp_path):
        """If the file has wrong number of columns, should raise."""
        import numpy as np

        rng = np.random.default_rng(1)
        lines = ["  1.0  2.0  3.0" for _ in range(20)]  # 3 cols, not 590
        (tmp_path / "secom.data").write_text("\n".join(lines))

        import src.data_ops.secom_schema as mod

        original_count = mod._FEATURE_COUNT
        original_cols = mod._FEATURE_COLUMNS
        try:
            mod._FEATURE_COUNT = 5
            mod._FEATURE_COLUMNS = [f"feature_{i:03d}" for i in range(1, 6)]
            with pytest.raises(ValueError, match="Expected"):
                mod.load_secom_data(tmp_path)
        finally:
            mod._FEATURE_COUNT = original_count
            mod._FEATURE_COLUMNS = original_cols

    def test_nan_values_preserved(self, tmp_path):
        """NaN markers in the file should become actual NaN in the DataFrame."""
        lines = ["NaN NaN 1.0 2.0 3.0" for _ in range(30)]
        (tmp_path / "secom.data").write_text("\n".join(lines))

        import src.data_ops.secom_schema as mod

        original_count = mod._FEATURE_COUNT
        original_cols = mod._FEATURE_COLUMNS
        try:
            mod._FEATURE_COUNT = 5
            mod._FEATURE_COLUMNS = [f"feature_{i:03d}" for i in range(1, 6)]
            df = mod.load_secom_data(tmp_path)
            assert df["feature_001"].isna().all()
            assert df["feature_002"].isna().all()
            assert not df["feature_003"].isna().any()
        finally:
            mod._FEATURE_COUNT = original_count
            mod._FEATURE_COLUMNS = original_cols


class TestLoadSecomLabels:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="secom_labels"):
            load_secom_labels("/nonexistent/path")

    def test_label_encoding(self, tmp_path):
        _write_fake_secom_labels(tmp_path, n_rows=100)
        df = load_secom_labels(tmp_path)

        assert len(df) == 100
        assert set(df["label"].unique()) <= {0, 1}
        assert set(df["label_name"].unique()) <= {"pass", "fail"}
        # -1 maps to 0=pass, 1 maps to 1=fail
        assert (df[df["raw_label"] == -1]["label"] == 0).all()
        assert (df[df["raw_label"] == 1]["label"] == 1).all()

    def test_sample_id_aligns_with_measurements(self, tmp_path):
        """Labels should have sequential sample_id starting at 1."""
        _write_fake_secom_labels(tmp_path, n_rows=10)
        df = load_secom_labels(tmp_path)
        assert df["sample_id"].tolist() == list(range(1, 11))

    def test_invalid_label_raises(self, tmp_path):
        """Unexpected label values should raise ValueError."""
        (tmp_path / "secom_labels.data").write_text(
            "\n".join(["-1", "1", "999", "-1", "1"])
        )
        with pytest.raises(ValueError, match="Unexpected label"):
            load_secom_labels(tmp_path)


class TestFeatureMissingness:
    def test_computes_missingness(self, tmp_path):
        """Feature missingness should be computed correctly."""
        # Create data where feature_001 is 50% NaN, feature_002 is 0% NaN
        lines = []
        for i in range(100):
            v1 = "NaN" if i < 50 else "0.0"
            v2 = "1.0"
            rest = "0.0 " * 3
            lines.append(f"{v1}  {v2}  {rest.strip()}")
        (tmp_path / "secom.data").write_text("\n".join(lines))

        import src.data_ops.secom_schema as mod

        original_count = mod._FEATURE_COUNT
        original_cols = mod._FEATURE_COLUMNS
        try:
            mod._FEATURE_COUNT = 5
            mod._FEATURE_COLUMNS = [f"feature_{i:03d}" for i in range(1, 6)]
            df = mod.load_secom_data(tmp_path)
            miss = mod.compute_feature_missingness(df)

            row1 = miss[miss["feature_name"] == "feature_001"].iloc[0]
            assert row1["missing_count"] == 50
            assert row1["missing_rate"] == 0.5

            row2 = miss[miss["feature_name"] == "feature_002"].iloc[0]
            assert row2["missing_count"] == 0
            assert row2["missing_rate"] == 0.0
        finally:
            mod._FEATURE_COUNT = original_count
            mod._FEATURE_COLUMNS = original_cols


class TestFeatureStats:
    def test_computes_stats(self, tmp_path):
        """Feature stats should compute correctly on known values."""
        # All 1.0 for feature_001
        lines = []
        for _ in range(50):
            lines.append("1.0  2.0  3.0  4.0  5.0")
        (tmp_path / "secom.data").write_text("\n".join(lines))

        import src.data_ops.secom_schema as mod

        original_count = mod._FEATURE_COUNT
        original_cols = mod._FEATURE_COLUMNS
        try:
            mod._FEATURE_COUNT = 5
            mod._FEATURE_COLUMNS = [f"feature_{i:03d}" for i in range(1, 6)]
            df = mod.load_secom_data(tmp_path)
            stats = mod.compute_feature_stats(df)

            row = stats[stats["feature_name"] == "feature_001"].iloc[0]
            assert row["mean"] == 1.0
            assert row["std"] == 0.0
            assert row["min"] == 1.0
            assert row["max"] == 1.0
        finally:
            mod._FEATURE_COUNT = original_count
            mod._FEATURE_COLUMNS = original_cols

    def test_all_nan_stats_are_none(self, tmp_path):
        """All-NaN features should have NaN stats (None → NaN in float64 col)."""
        lines = []
        for _ in range(20):
            lines.append("NaN  1.0  2.0  3.0  4.0")
        (tmp_path / "secom.data").write_text("\n".join(lines))

        import src.data_ops.secom_schema as mod

        original_count = mod._FEATURE_COUNT
        original_cols = mod._FEATURE_COLUMNS
        try:
            mod._FEATURE_COUNT = 5
            mod._FEATURE_COLUMNS = [f"feature_{i:03d}" for i in range(1, 6)]
            df = mod.load_secom_data(tmp_path)
            stats = mod.compute_feature_stats(df)

            import pandas as pd

            row = stats[stats["feature_name"] == "feature_001"].iloc[0]
            # pandas converts Python None → NaN in float64 columns
            assert pd.isna(row["mean"])
            assert pd.isna(row["std"])

            # Feature with real values should have non-NaN stats
            row2 = stats[stats["feature_name"] == "feature_002"].iloc[0]
            assert not pd.isna(row2["mean"])
            assert row2["mean"] == 1.0
        finally:
            mod._FEATURE_COUNT = original_count
            mod._FEATURE_COLUMNS = original_cols


class TestSchemaInfo:
    def test_returns_valid_metadata(self):
        info = get_schema_info()
        assert info["feature_count"] == 590
        assert len(info["feature_columns"]) == 590
        assert info["expected_rows"] == 1567
        assert info["label_map"]["raw"] == {-1: 0, 1: 1}
        assert info["expected_labels"] == {"pass": 1463, "fail": 104}
