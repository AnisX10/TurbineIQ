from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from typing import Any

GLB_PATH = Path(__file__).resolve().parents[1] / "frontend" / "public" / "models" / "turbine.glb"


def _read_glb_document() -> dict[str, Any]:
    blob = GLB_PATH.read_bytes()
    magic, version, declared_length = struct.unpack_from("<4sII", blob)
    assert magic == b"glTF"
    assert version == 2
    assert declared_length == len(blob)

    json_length, json_chunk_type = struct.unpack_from("<II", blob, 12)
    assert json_chunk_type == 0x4E4F534A
    return json.loads(blob[20 : 20 + json_length].decode("utf-8"))


def _mesh_nodes(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [node for node in document["nodes"] if "mesh" in node]


def test_turbine_bucket_castings_are_individually_selectable() -> None:
    nodes = _mesh_nodes(_read_glb_document())
    stage_one_buckets = [
        node
        for node in nodes
        if node["name"].startswith("Stage 1 rotating buckets | bucket casting proxy")
    ]

    assert len(stage_one_buckets) == 24
    assert len({node["name"] for node in stage_one_buckets}) == 24
    for node in stage_one_buckets:
        extras = node["extras"]
        assert extras["row_instance_count"] == 24
        assert extras["public_component_envelope_mm"] == "267 x 124 x 52"
        assert extras["public_component_mass_kg"] == 2.8
        assert "one bucket casting" in extras["envelope_note"]
        assert "not scaled" in extras["envelope_note"]


def test_turbine_nozzle_vane_is_not_given_stage_casting_dimensions_as_its_own() -> None:
    nodes = _mesh_nodes(_read_glb_document())
    stage_one_vanes = [
        node
        for node in nodes
        if node["name"].startswith("Stage 1 nozzle guide vanes | nozzle vane proxy")
    ]

    assert len(stage_one_vanes) == 26
    for node in stage_one_vanes:
        extras = node["extras"]
        assert "public_component_envelope_mm" not in extras
        assert "public_component_mass_kg" not in extras
        assert extras["public_reference_envelope_mm"] == "357 x 208 x 153"
        assert extras["public_reference_mass_kg"] == 9.5
        assert "not for an individual vane" in extras["reference_note"]


def test_exported_rotor_names_match_the_viewer_animation_contract() -> None:
    names = [node["name"] for node in _mesh_nodes(_read_glb_document())]
    normalized = [re.sub(r"[^a-z0-9]+", " ", name.lower()).strip() for name in names]

    assert normalized.count("main rotor shaft") == 1
    assert sum(name.startswith("compressor rotor stage") for name in normalized) == 17
    assert sum(name.startswith("compressor rotor disk rim") for name in normalized) == 17
    assert sum("bucket casting proxy" in name for name in normalized) == 66
    rotor_wheels = sum(
        name.startswith("stage ") and name.endswith(" rotor wheel") for name in normalized
    )
    assert rotor_wheels == 3
