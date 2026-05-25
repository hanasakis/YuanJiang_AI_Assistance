"""Build SECOM DuckDB database from parsed DataFrames.

Reads raw SECOM data via secom_schema.py, builds four analytical tables
in data/processed/secom.duckdb.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from src.data_ops.secom_schema import (
    compute_feature_missingness,
    compute_feature_stats,
    load_secom_data,
    load_secom_labels,
)

_DB_PATH = Path("data/processed/secom.duckdb")


def build_database(
    raw_dir: str | Path = "data/raw",
    db_path: str | Path = _DB_PATH,
    overwrite: bool = True,
) -> Path:
    """Build the SECOM DuckDB database.

    Args:
        raw_dir: Directory containing secom.data and secom_labels.data.
        db_path: Output DuckDB file path.
        overwrite: If True, delete existing database before rebuilding.

    Returns:
        Path to the built DuckDB file.

    Raises:
        FileNotFoundError: If raw data files are missing.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if overwrite and db_path.exists():
        db_path.unlink()

    print("Loading SECOM data...")
    measurements = load_secom_data(raw_dir)
    labels = load_secom_labels(raw_dir)
    missingness = compute_feature_missingness(measurements)
    stats = compute_feature_stats(measurements)

    print(f"  measurements: {measurements.shape[0]} rows x {measurements.shape[1]} cols")
    print(f"  labels:       {labels.shape[0]} rows")
    print(f"  missingness:  {missingness.shape[0]} features")
    print(f"  stats:        {stats.shape[0]} features")

    print(f"Writing to {db_path}...")
    con = duckdb.connect(str(db_path))

    con.execute("""
        CREATE TABLE secom_measurements (
            sample_id INTEGER PRIMARY KEY,
            feature_001 DOUBLE, feature_002 DOUBLE, feature_003 DOUBLE,
            feature_004 DOUBLE, feature_005 DOUBLE, feature_006 DOUBLE
            -- Full 590-column schema expanded at INSERT time
        )
    """)

    # DuckDB can ingest pandas DataFrames directly
    con.execute("DROP TABLE IF EXISTS secom_measurements")
    con.execute("CREATE TABLE secom_measurements AS SELECT * FROM measurements")

    con.execute("DROP TABLE IF EXISTS secom_labels")
    con.execute("""
        CREATE TABLE secom_labels (
            sample_id INTEGER PRIMARY KEY,
            raw_label INTEGER,
            label TINYINT,
            label_name VARCHAR
        )
    """)
    con.execute("INSERT INTO secom_labels SELECT * FROM labels")

    con.execute("DROP TABLE IF EXISTS feature_missingness")
    con.execute("""
        CREATE TABLE feature_missingness (
            feature_name VARCHAR PRIMARY KEY,
            total_samples INTEGER,
            missing_count INTEGER,
            missing_rate DOUBLE
        )
    """)
    con.execute("INSERT INTO feature_missingness SELECT * FROM missingness")

    con.execute("DROP TABLE IF EXISTS feature_stats")
    con.execute("""
        CREATE TABLE feature_stats (
            feature_name VARCHAR PRIMARY KEY,
            mean DOUBLE,
            std DOUBLE,
            min DOUBLE,
            p25 DOUBLE,
            median DOUBLE,
            p75 DOUBLE,
            max DOUBLE
        )
    """)
    con.execute("INSERT INTO feature_stats SELECT * FROM stats")

    # Verify
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    print(f"Tables created: {[t[0] for t in tables]}")

    row_counts = {
        table[0]: con.execute(f"SELECT count(*) FROM {table[0]}").fetchone()[0]
        for table in tables
    }
    for name, count in row_counts.items():
        print(f"  {name}: {count} rows")

    con.close()
    print("Done.")
    return db_path


def verify_database(db_path: str | Path = _DB_PATH) -> dict:
    """Verify the built SECOM database integrity.

    Args:
        db_path: Path to the DuckDB file.

    Returns:
        Dict with verification results.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return {"status": "missing", "error": f"{db_path} not found"}

    con = duckdb.connect(str(db_path))
    results: dict = {"status": "ok", "tables": {}, "issues": []}

    try:
        # Check row counts
        n_meas = con.execute(
            "SELECT count(*) FROM secom_measurements"
        ).fetchone()[0]
        n_labels = con.execute(
            "SELECT count(*) FROM secom_labels"
        ).fetchone()[0]

        results["tables"]["secom_measurements"] = n_meas
        results["tables"]["secom_labels"] = n_labels

        if n_meas != 1567:
            results["issues"].append(
                f"secom_measurements has {n_meas} rows, expected 1567"
            )
        if n_labels != 1567:
            results["issues"].append(
                f"secom_labels has {n_labels} rows, expected 1567"
            )

        # Check label distribution
        dist = con.execute("""
            SELECT label, count(*) as cnt
            FROM secom_labels
            GROUP BY label
            ORDER BY label
        """).fetchall()
        results["tables"]["label_distribution"] = {str(r[0]): r[1] for r in dist}

        # Check feature count
        col_count = con.execute("""
            SELECT count(*)
            FROM information_schema.columns
            WHERE table_name = 'secom_measurements'
        """).fetchone()[0]
        # sample_id + 590 features = 591 columns
        if col_count != 591:
            results["issues"].append(
                f"secom_measurements has {col_count} columns, expected 591"
            )

        if results["issues"]:
            results["status"] = "warning"

    finally:
        con.close()

    return results


if __name__ == "__main__":
    build_database()
    result = verify_database()
    print()
    print("Verification:", result["status"])
    for issue in result.get("issues", []):
        print(f"  [!] {issue}")
