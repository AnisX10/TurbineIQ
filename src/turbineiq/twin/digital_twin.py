"""Offline digital-twin demonstrator driven only by generated scenarios."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from turbineiq.analytics import detect_anomalies
from turbineiq.synthetic import SCENARIOS, generate_scenario

SYNTHETIC_ASSET_ID = "TIQ-SYNTH-GT-001"
MODEL_NAME = "Simplified single-shaft open-cycle Brayton model"


@dataclass(frozen=True)
class TwinMetric:
    """One labeled value rendered in a component inspector."""

    key: str
    label: str
    value: float | bool
    unit: str
    provenance: str
    reference_value: float | None = None

    def to_dict(self) -> dict[str, str | float | bool | None]:
        return asdict(self)


@dataclass(frozen=True)
class TwinComponentState:
    """Synthetic component state keyed independently from Blender mesh names."""

    component_id: str
    label: str
    status: str
    status_label: str
    summary: str
    metrics: tuple[TwinMetric, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "label": self.label,
            "status": self.status,
            "status_label": self.status_label,
            "summary": self.summary,
            "metrics": [metric.to_dict() for metric in self.metrics],
        }


@dataclass(frozen=True)
class TwinSnapshot:
    """One time-aligned model state and generated observation for the asset."""

    asset_id: str
    sample_index: int
    timestamp_utc: str
    scenario_id: str
    scenario_name: str
    seed: int
    ambient_temperature_c: float
    ambient_pressure_kpa: float
    compressor_efficiency_assumption: float
    synthetic_true_compressor_efficiency: float
    compressor_discharge_temperature_k: float
    reference_compressor_discharge_temperature_k: float
    turbine_inlet_temperature_k: float
    exhaust_temperature_k: float
    reference_exhaust_temperature_k: float
    model_electrical_power_kw: float
    synthetic_truth_electrical_power_kw: float
    synthetic_observed_power_kw: float
    power_residual_kw: float
    residual_percent: float
    sensor_fault_label: str
    sensor_fault_injected: bool
    residual_screen_flag: bool
    components: tuple[TwinComponentState, ...]
    data_provenance: str = "seeded synthetic scenario"

    @property
    def screen_status(self) -> str:
        if self.residual_screen_flag:
            return "Synthetic residual flagged"
        return "No residual flag at this sample"

    @property
    def scenario_perturbation_label(self) -> str:
        if self.scenario_id == "compressor_fouling":
            return "synthetic_compressor_efficiency_drift"
        if self.sensor_fault_injected:
            return self.sensor_fault_label
        return "none"

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["components"] = [component.to_dict() for component in self.components]
        result["screen_status"] = self.screen_status
        result["scenario_perturbation_label"] = self.scenario_perturbation_label
        return result


@dataclass(frozen=True)
class DigitalTwinRun:
    """A local synthetic asset record synchronized to one generated timeline."""

    scenario_id: str
    scenario_name: str
    seed: int
    history: pd.DataFrame
    analyzed_history: pd.DataFrame
    scenario_description: str = ""
    asset_id: str = SYNTHETIC_ASSET_ID

    def __post_init__(self) -> None:
        if self.scenario_id not in SCENARIOS:
            raise ValueError(f"unknown scenario_id {self.scenario_id!r}")
        if self.history.empty or self.analyzed_history.empty:
            raise ValueError("digital-twin history must contain at least one sample")
        if "synthetic_data" not in self.history:
            raise ValueError("digital-twin input must be explicitly marked synthetic")
        if not bool(self.history["synthetic_data"].fillna(False).all()):
            raise ValueError("digital-twin input must contain synthetic data only")
        if len(self.history) != len(self.analyzed_history):
            raise ValueError("analyzed history must match the synthetic history length")

    @property
    def sample_count(self) -> int:
        return len(self.history)

    @property
    def model_name(self) -> str:
        return str(self.history.attrs.get("model_name", MODEL_NAME))

    def snapshot_at(self, sample_index: int) -> TwinSnapshot:
        """Return the asset, model, and component state at one generated step."""

        if not isinstance(sample_index, int) or not 0 <= sample_index < self.sample_count:
            raise ValueError(f"sample_index must be between 0 and {self.sample_count - 1}")

        row = self.analyzed_history.iloc[sample_index]
        model_power = float(row["model_electrical_power_kw"])
        observed_power = float(row["observed_electrical_power_kw"])
        residual = float(row["power_residual_kw"])
        residual_percent = residual / max(abs(model_power), 1.0) * 100.0
        fault_injected = bool(row["sensor_fault_injected"])
        residual_flag = bool(row["anomaly_flag"])
        components = _component_states(
            row,
            scenario_id=self.scenario_id,
            sensor_fault_injected=fault_injected,
            residual_screen_flag=residual_flag,
        )

        return TwinSnapshot(
            asset_id=self.asset_id,
            sample_index=sample_index,
            timestamp_utc=pd.Timestamp(row["timestamp_utc"]).isoformat(),
            scenario_id=self.scenario_id,
            scenario_name=self.scenario_name,
            seed=self.seed,
            ambient_temperature_c=float(row["ambient_temperature_c"]),
            ambient_pressure_kpa=float(row["ambient_pressure_kpa"]),
            compressor_efficiency_assumption=float(row["compressor_efficiency_assumption"]),
            synthetic_true_compressor_efficiency=float(
                row["synthetic_true_compressor_efficiency"]
            ),
            compressor_discharge_temperature_k=float(row["compressor_discharge_temperature_k"]),
            reference_compressor_discharge_temperature_k=float(
                row["reference_compressor_discharge_temperature_k"]
            ),
            turbine_inlet_temperature_k=float(row["turbine_inlet_temperature_k"]),
            exhaust_temperature_k=float(row["exhaust_temperature_k"]),
            reference_exhaust_temperature_k=float(row["reference_exhaust_temperature_k"]),
            model_electrical_power_kw=model_power,
            synthetic_truth_electrical_power_kw=float(
                row["synthetic_truth_electrical_power_kw"]
            ),
            synthetic_observed_power_kw=observed_power,
            power_residual_kw=residual,
            residual_percent=residual_percent,
            sensor_fault_label=str(row["sensor_fault_label"]),
            sensor_fault_injected=fault_injected,
            residual_screen_flag=residual_flag,
            components=components,
        )

    def to_payload(self, sample_index: int) -> dict[str, object]:
        """Return a JSON-friendly run payload for the local API and viewer."""

        if not isinstance(sample_index, int) or not 0 <= sample_index < self.sample_count:
            raise ValueError(f"sample_index must be between 0 and {self.sample_count - 1}")
        frame = self.analyzed_history.copy()
        frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True).map(
            lambda value: value.isoformat()
        )
        snapshots = [self.snapshot_at(index).to_dict() for index in range(self.sample_count)]
        return {
            "run": {
                "asset_id": self.asset_id,
                "scenario_id": self.scenario_id,
                "scenario_name": self.scenario_name,
                "scenario_description": self.scenario_description,
                "seed": self.seed,
                "sample_count": self.sample_count,
                "sample_interval_minutes": 15,
                "model_name": self.model_name,
                "synthetic_only": True,
                "data_provenance": "seeded synthetic scenario",
            },
            "snapshot": snapshots[sample_index],
            "snapshots": snapshots,
            "timeline": frame.to_dict(orient="records"),
        }


def _metric(
    key: str,
    label: str,
    value: float | bool,
    unit: str,
    provenance: str,
    reference_value: float | None = None,
) -> TwinMetric:
    return TwinMetric(key, label, value, unit, provenance, reference_value)


def _component_states(
    row: pd.Series,
    *,
    scenario_id: str,
    sensor_fault_injected: bool,
    residual_screen_flag: bool,
) -> tuple[TwinComponentState, ...]:
    compressor_status = (
        "scenario_perturbation" if scenario_id == "compressor_fouling" else "nominal"
    )
    generator_status = "nominal"
    generator_status_label = "Model comparison"
    generator_summary = "Synthetic observation compared with the reference cycle model."
    if residual_screen_flag:
        generator_status = "residual_screen"
        generator_status_label = "Residual screen"
        generator_summary = "The output residual is flagged by a robust statistical screen."
    if sensor_fault_injected:
        generator_status = "synthetic_measurement_fault"
        generator_status_label = "Injected sensor event"
        generator_summary = "A labeled synthetic power-sensor spike was injected at this sample."

    return (
        TwinComponentState(
            component_id="inlet",
            label="Air inlet",
            status="scenario_context" if scenario_id == "warm_ambient" else "nominal",
            status_label="Scenario context" if scenario_id == "warm_ambient" else "Modelled",
            summary="Synthetic inlet conditions used by the selected scenario.",
            metrics=(
                _metric(
                    "ambient_temperature_c",
                    "Ambient temperature",
                    float(row["ambient_temperature_c"]),
                    "°C",
                    "Synthetic scenario input",
                ),
                _metric(
                    "ambient_pressure_kpa",
                    "Ambient absolute pressure",
                    float(row["ambient_pressure_kpa"]),
                    "kPa abs",
                    "Synthetic scenario input",
                ),
                _metric(
                    "air_mass_flow_kg_s",
                    "Air mass flow",
                    float(row["air_mass_flow_kg_s_assumption"]),
                    "kg/s",
                    "Fixed-volume density assumption",
                ),
            ),
        ),
        TwinComponentState(
            component_id="compressor",
            label="Compressor",
            status=compressor_status,
            status_label=(
                "Synthetic parameter drift"
                if compressor_status == "scenario_perturbation"
                else "Modelled"
            ),
            summary=(
                "Synthetic compressor-efficiency drift is compared with a fixed "
                "reference assumption."
                if compressor_status == "scenario_perturbation"
                else "Compressor state calculated from the selected scenario inputs."
            ),
            metrics=(
                _metric(
                    "compressor_efficiency",
                    "Synthetic efficiency parameter",
                    float(row["synthetic_true_compressor_efficiency"]),
                    "fraction",
                    "Known synthetic scenario truth",
                    float(row["compressor_efficiency_assumption"]),
                ),
                _metric(
                    "compressor_discharge_temperature_k",
                    "Discharge temperature",
                    float(row["compressor_discharge_temperature_k"]),
                    "K",
                    "Synthetic plant-model state",
                    float(row["reference_compressor_discharge_temperature_k"]),
                ),
                _metric(
                    "compressor_power_kw",
                    "Compressor power",
                    float(row["compressor_power_kw"]),
                    "kW",
                    "Synthetic plant-model state",
                    float(row["reference_compressor_power_kw"]),
                ),
            ),
        ),
        TwinComponentState(
            component_id="combustor",
            label="Combustor",
            status="nominal",
            status_label="Modelled",
            summary="Combustor values are simplified cycle-model calculations and assumptions.",
            metrics=(
                _metric(
                    "turbine_inlet_temperature_k",
                    "Turbine inlet temperature",
                    float(row["turbine_inlet_temperature_k"]),
                    "K",
                    "Synthetic plant-model state",
                    float(row["reference_turbine_inlet_temperature_k"]),
                ),
                _metric(
                    "combustor_pressure_loss_fraction",
                    "Pressure-loss assumption",
                    float(row["combustor_pressure_loss_fraction"]),
                    "fraction",
                    "Illustrative cycle-model assumption",
                ),
                _metric(
                    "combustor_heat_input_kw",
                    "Heat input estimate",
                    float(row["combustor_heat_input_kw"]),
                    "kW",
                    "Simplified cycle-model calculation",
                ),
            ),
        ),
        TwinComponentState(
            component_id="turbine",
            label="Turbine",
            status="nominal",
            status_label="Modelled",
            summary="Turbine gas-path values come from the simplified cycle calculation.",
            metrics=(
                _metric(
                    "exhaust_temperature_k",
                    "Exhaust temperature",
                    float(row["exhaust_temperature_k"]),
                    "K",
                    "Synthetic plant-model state",
                    float(row["reference_exhaust_temperature_k"]),
                ),
                _metric(
                    "turbine_power_kw",
                    "Turbine power",
                    float(row["turbine_power_kw"]),
                    "kW",
                    "Synthetic plant-model state",
                    float(row["reference_turbine_power_kw"]),
                ),
            ),
        ),
        TwinComponentState(
            component_id="shaft",
            label="Single shaft",
            status="nominal",
            status_label="Modelled",
            summary="Shaft power is derived from net cycle power and mechanical efficiency.",
            metrics=(
                _metric(
                    "shaft_power_kw",
                    "Shaft power estimate",
                    float(row["shaft_power_kw"]),
                    "kW",
                    "Synthetic plant-model state",
                    float(row["reference_shaft_power_kw"]),
                ),
            ),
        ),
        TwinComponentState(
            component_id="generator",
            label="Generator",
            status=generator_status,
            status_label=generator_status_label,
            summary=generator_summary,
            metrics=(
                _metric(
                    "model_electrical_power_kw",
                    "Reference model output",
                    float(row["model_electrical_power_kw"]),
                    "kW",
                    "Reference cycle model",
                ),
                _metric(
                    "observed_electrical_power_kw",
                    "Synthetic observed output",
                    float(row["observed_electrical_power_kw"]),
                    "kW",
                    "Generated plant output plus measurement noise",
                ),
                _metric(
                    "power_residual_kw",
                    "Output residual",
                    float(row["power_residual_kw"]),
                    "kW",
                    "Synthetic observation minus reference model",
                ),
            ),
        ),
    )


def create_synthetic_twin(
    scenario_id: str = "sensor_fault",
    *,
    seed: int = 42,
    samples: int = 96,
) -> DigitalTwinRun:
    """Generate a digital-twin state timeline without reading physical data."""

    if scenario_id not in SCENARIOS:
        raise ValueError(f"unknown scenario_id {scenario_id!r}")
    history = generate_scenario(scenario_id, seed=seed, samples=samples)
    analyzed = detect_anomalies(history)
    spec = SCENARIOS[scenario_id]
    return DigitalTwinRun(
        scenario_id=scenario_id,
        scenario_name=spec.name,
        seed=seed,
        history=history,
        analyzed_history=analyzed,
        scenario_description=spec.description,
    )
