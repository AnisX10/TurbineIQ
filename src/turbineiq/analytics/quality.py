"""Local checks for synthetic operating-data quality and robust outliers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite

import numpy as np
import pandas as pd

POSITIVE_COLUMNS = (
    "ambient_pressure_kpa",
    "pressure_ratio",
    "compressor_discharge_temperature_k",
    "turbine_inlet_temperature_k",
    "exhaust_temperature_k",
    "model_electrical_power_kw",
    "observed_electrical_power_kw",
    "fuel_mass_flow_kg_s",
)
FLATLINE_CHANNELS = (
    "ambient_temperature_c",
    "compressor_discharge_temperature_k",
    "observed_electrical_power_kw",
    "power_residual_kw",
)


@dataclass(frozen=True)
class DataQualityReport:
    row_count: int
    column_count: int
    missing_cells: int
    duplicate_timestamps: int
    out_of_order_timestamps: int
    invalid_numeric_counts: dict[str, int]
    flatline_columns: tuple[str, ...]
    non_synthetic_rows: int
    findings: tuple[str, ...]

    @property
    def passes(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["flatline_columns"] = list(self.flatline_columns)
        result["findings"] = list(self.findings)
        result["passes"] = self.passes
        return result


def assess_data_quality(
    frame: pd.DataFrame,
    *,
    timestamp_column: str = "timestamp_utc",
    minimum_flatline_points: int = 8,
) -> DataQualityReport:
    """Check missingness, time order, physical positivity, labels, and flatlines.

    Positivity checks cover absolute pressures, temperatures in kelvin, flow,
    power, and pressure ratio. They are mathematical sanity checks, not OEM
    operating limits.
    """

    if minimum_flatline_points < 2:
        raise ValueError("minimum_flatline_points must be at least 2")

    findings: list[str] = []
    missing_cells = int(frame.isna().to_numpy().sum())
    if missing_cells:
        findings.append(f"{missing_cells} missing cell(s) found")

    duplicate_timestamps = 0
    out_of_order_timestamps = 0
    if timestamp_column not in frame:
        findings.append(f"required timestamp column {timestamp_column!r} is missing")
    else:
        timestamps = pd.to_datetime(frame[timestamp_column], errors="coerce", utc=True)
        duplicate_timestamps = int(timestamps.duplicated().sum())
        out_of_order_timestamps = int(timestamps.dropna().diff().lt(pd.Timedelta(0)).sum())
        if duplicate_timestamps:
            findings.append(f"{duplicate_timestamps} duplicate timestamp(s) found")
        if out_of_order_timestamps:
            findings.append(f"{out_of_order_timestamps} timestamp(s) are out of order")

    invalid_numeric_counts: dict[str, int] = {}
    for column in POSITIVE_COLUMNS:
        if column not in frame:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        invalid_count = int((numeric.notna() & (numeric <= 0)).sum())
        invalid_numeric_counts[column] = invalid_count
        if invalid_count:
            findings.append(f"{invalid_count} non-positive value(s) in {column}")

    flatline_columns: list[str] = []
    for column in FLATLINE_CHANNELS:
        if column not in frame:
            continue
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if len(values) >= minimum_flatline_points and values.nunique() == 1:
            flatline_columns.append(column)
            findings.append(f"{column} is flat across {len(values)} non-missing row(s)")

    if "synthetic_data" in frame:
        synthetic_labels = frame["synthetic_data"].fillna(False).astype(bool)
        non_synthetic_rows = int((~synthetic_labels).sum())
        if non_synthetic_rows:
            findings.append(f"{non_synthetic_rows} row(s) are not marked synthetic")
    else:
        non_synthetic_rows = len(frame)
        if len(frame):
            findings.append("dataset has no synthetic_data label")

    return DataQualityReport(
        row_count=len(frame),
        column_count=len(frame.columns),
        missing_cells=missing_cells,
        duplicate_timestamps=duplicate_timestamps,
        out_of_order_timestamps=out_of_order_timestamps,
        invalid_numeric_counts=invalid_numeric_counts,
        flatline_columns=tuple(flatline_columns),
        non_synthetic_rows=non_synthetic_rows,
        findings=tuple(findings),
    )


def detect_anomalies(
    frame: pd.DataFrame,
    *,
    column: str = "power_residual_kw",
    threshold: float = 3.5,
) -> pd.DataFrame:
    """Add a signed robust z-score and flag large deviations from the median.

    The score uses the median absolute deviation (MAD), a robust scale estimate.
    If MAD is zero but values vary, population standard deviation is used as a
    finite fallback. The flag is an explainable screening signal, not a failure
    diagnosis or machine-specific alarm limit.
    """

    if column not in frame:
        raise ValueError(f"column {column!r} is not present")
    if not isfinite(float(threshold)) or threshold <= 0:
        raise ValueError("threshold must be a finite number greater than zero")

    values = pd.to_numeric(frame[column], errors="coerce")
    median = float(values.median()) if values.notna().any() else 0.0
    deviations = (values - median).abs()
    mad = float(deviations.median()) if deviations.notna().any() else 0.0
    if mad > 0:
        scale = 1.4826 * mad
    else:
        scale = float(values.std(ddof=0)) if values.notna().any() else 0.0

    if scale > 0:
        score = (values - median) / scale
    else:
        score = pd.Series(0.0, index=frame.index, dtype=float)
    score = score.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    result = frame.copy()
    result["robust_z_score"] = score
    result["anomaly_flag"] = score.abs() >= threshold
    result["anomaly_method"] = "median absolute deviation"
    return result
