"""Data-quality checks and explainable anomaly flags."""

from .quality import (
    DataQualityReport,
    assess_data_quality,
    detect_anomalies,
    detect_drift,
    screen_residual,
)

__all__ = [
    "DataQualityReport",
    "assess_data_quality",
    "detect_anomalies",
    "detect_drift",
    "screen_residual",
]
