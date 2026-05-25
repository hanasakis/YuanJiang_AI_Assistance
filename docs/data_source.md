# SECOM Dataset — Data Source Documentation

## Source

| Field | Value |
|-------|-------|
| **Dataset** | SECOM (Semiconductor Manufacturing Process) |
| **Origin** | UCI Machine Learning Repository |
| **URL** | https://archive.ics.uci.edu/dataset/179/secom |
| **DOI** | 10.24432/C54305 |
| **Citation** | McCann, M. & Johnston, A. (2008). SECOM. UCI Machine Learning Repository. |
| **License** | CC BY 4.0 (Creative Commons Attribution) |
| **Download Date** | (set on first download) |

## Dataset Description

SECOM contains 1567 wafer samples from a semiconductor fabrication line.
Each sample has 590 anonymized sensor measurements recorded during
manufacturing. The task is to predict which wafers will fail QA testing.

### Files

| File | Rows | Columns | Description |
|------|------|---------|-------------|
| `secom.data` | 1,567 | 590 | Sensor measurements (space-separated, NaN for missing) |
| `secom_labels.data` | 1,567 | 1 | Pass (-1) / Fail (1) label per sample |

### Anonymized Features

**All 590 features are anonymized.** The original column names — sensor IDs,
process step identifiers, tool chamber numbers — have been deliberately
removed before publication. Column positions are numbered 1 through 590.

> **Critical constraint for this project:**
> Anonymized features can be used for statistical anomaly detection
> (e.g., "feature_042 deviates 4.7σ from its training mean") but CANNOT
> be interpreted as specific physical root causes (e.g., "chamber pressure
> in etcher #3"). Any claim that maps an anonymous feature to a named
> tool, parameter, or process step is fabrication.

### Missing Values

SECOM has severe missingness — many features have > 50% NaN rates.
This is typical for semiconductor data where different sensors activate
at different process stages.

| Statistic | Value |
|-----------|-------|
| Total values | 924,530 (1,567 × 590) |
| Missing values | ~41,951 (4.54%) |
| Features with > 50% missing | ~12 |

### Label Distribution

| Label | Count | % |
|-------|-------|---|
| Pass (-1) | 1,463 | 93.4% |
| Fail (1) | 104 | 6.6% |

The dataset is heavily imbalanced — only 6.6% of samples are failures.

## Why Anonymized Features Still Have Analytical Value

1. **Statistical baselines work without names.** You don't need to know
   what a sensor measures to know that 4σ from its historical mean is
   an anomaly. The distribution itself is the signal.

2. **Cross-feature correlation patterns.** Even unnamed, correlated
   sensor clusters may indicate a process stage drifting together.

3. **Triage, not root cause.** The model tells the engineer *which wafers*
   to inspect and *which features* deviate — it does not claim to know
   *why*. Root cause analysis remains a human task requiring domain
   knowledge of the physical tools.

4. **Generalizable to any anonymized monitoring data.** Manufacturing
   partners routinely anonymize process data before sharing. Methods
   validated on SECOM transfer directly to those scenarios.

## Processing Pipeline

```
data/raw/secom.data ──────────┐
data/raw/secom_labels.data ───┤
                               │
                               ▼
                    src/data_ops/secom_schema.py
                      · parse space-separated floats
                      · assign sample_id (1..1567)
                      · map labels: -1→0 (pass), 1→1 (fail)
                               │
                               ▼
                    src/data_ops/build_duckdb.py
                      · DuckDB tables:
                        - secom_measurements
                        - secom_labels
                        - feature_missingness
                        - feature_stats
                               │
                               ▼
                    data/processed/secom.duckdb
```
