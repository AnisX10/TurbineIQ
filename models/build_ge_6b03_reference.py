"""Build an interactive, source-noted GE 6B.03 reference visualization.

The machine's published performance values and family architecture are kept as
metadata. No undisclosed overall dimensions or OEM component geometry are
inferred. Geometry is a visual proxy and the assembly envelope is not to scale.

Run with Blender:
    blender --background --python models/build_ge_6b03_reference.py
"""

from __future__ import annotations

import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

PROJECT = Path(__file__).resolve().parents[1]
BLEND_PATH = PROJECT / "models" / "ge_6b03_reference.blend"
GLB_PATH = PROJECT / "frontend" / "public" / "models" / "turbine.glb"
PREVIEW_PATH = PROJECT / "models" / "ge_6b03_reference_preview.png"

GE_CATALOG = (
    "https://www.gevernova.com/content/dam/gepower-new/global/en_US/"
    "downloads/gas-new-site/catalog/GEA35241-2025-GE-Vernova-Gas-Power-Catalog.pdf"
)
GE_UPRATE = (
    "https://www.ge.com/content/dam/gepower-new/global/en_US/downloads/"
    "gas-new-site/resources/reference/ger-4217b-uprate-options-ms6001-"
    "heavy-duty-gas-turbine.pdf"
)
BHEL_EOI = (
    "https://www.bhel.com/sites/default/files/EOI-Nozzle%20and%20Bucket%20"
    "Investment%20castings%20Rev-00.pdf"
)

ANGLE_START = 180.0
ANGLE_END = 400.0
TAU = math.tau


def material(name: str, color: tuple[float, float, float], metallic: float, roughness: float):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    return mat


MATERIALS = {}


def create_materials():
    global MATERIALS
    MATERIALS = {
        "casing": material("Titanium | graphite blue", (0.12, 0.20, 0.25), 0.78, 0.28),
        "casing_light": material("Machined | cool steel", (0.40, 0.51, 0.56), 0.84, 0.24),
        "rotor": material("Rotor | satin nickel", (0.63, 0.70, 0.71), 0.88, 0.22),
        "stator": material("Stator | titanium", (0.28, 0.40, 0.44), 0.78, 0.29),
        "hot": material("Hot gas path | copper alloy", (0.78, 0.33, 0.13), 0.72, 0.25),
        "hot_light": material("Hot gas path | pale alloy", (0.91, 0.57, 0.26), 0.72, 0.23),
        "dark": material("Recess | carbon steel", (0.045, 0.075, 0.09), 0.52, 0.4),
        "accent": material("Identification | muted teal", (0.16, 0.56, 0.60), 0.55, 0.3),
        "ground": material("Stage | midnight", (0.025, 0.045, 0.058), 0.28, 0.52),
    }

MODEL_COLLECTION = None
PRESENTATION_COLLECTION = None
ASSET_ROOT = None
COMPONENT_ROOTS = {}
MODEL_OBJECTS = []


def link_object(obj, parent=None, collection=None, model=True):
    (collection or MODEL_COLLECTION).objects.link(obj)
    if parent is not None:
        obj.parent = parent
    if model:
        MODEL_OBJECTS.append(obj)
    return obj


def empty(name: str, component_id: str | None = None):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.16
    link_object(obj, ASSET_ROOT)
    if component_id:
        obj["component_id"] = component_id
    return obj


def make_mesh(name, vertices, faces, mat, parent, *, smooth=True, props=None):
    mesh = bpy.data.meshes.new(name + " | mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    if bm.faces:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    link_object(obj, parent)
    obj.data.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    if props:
        for key, value in props.items():
            obj[key] = value
    return obj


def ring_coords(x, radius, center_y, center_z, angle, tube_offset=0.0):
    radial = radius + tube_offset
    return (x, center_y + radial * math.cos(angle), center_z + radial * math.sin(angle))


def make_tube_x(name, parent, x0, x1, r_outer0, r_outer1=None, *,
                r_inner0=0.0, r_inner1=None, center_y=0.0, center_z=0.0,
                mat=None, segments=64, props=None):
    """Annular cylinder or diffuser with an axis parallel to X."""
    r_outer1 = r_outer0 if r_outer1 is None else r_outer1
    r_inner1 = r_inner0 if r_inner1 is None else r_inner1
    angles = [TAU * i / segments for i in range(segments)]
    vertices = []
    for x, radius in ((x0, r_outer0), (x1, r_outer1)):
        vertices.extend((x, center_y + radius * math.cos(a), center_z + radius * math.sin(a)) for a in angles)
    outer0 = 0
    outer1 = segments
    faces = []
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((outer0 + i, outer0 + j, outer1 + j, outer1 + i))
    if r_inner0 > 0.0 and r_inner1 > 0.0:
        inner0, inner1 = len(vertices), len(vertices) + segments
        for x, radius in ((x0, r_inner0), (x1, r_inner1)):
            vertices.extend((x, center_y + radius * math.cos(a), center_z + radius * math.sin(a)) for a in angles)
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((inner0 + j, inner0 + i, inner1 + i, inner1 + j))
            faces.append((outer0 + i, inner0 + i, inner0 + j, outer0 + j))
            faces.append((outer1 + j, inner1 + j, inner1 + i, outer1 + i))
    else:
        center0, center1 = len(vertices), len(vertices) + 1
        vertices.extend(((x0, center_y, center_z), (x1, center_y, center_z)))
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((center0, outer0 + j, outer0 + i))
            faces.append((center1, outer1 + i, outer1 + j))
    return make_mesh(name, vertices, faces, mat or MATERIALS["casing"], parent, props=props)


def make_torus_x(name, parent, x, radius, tube_radius, mat, *,
                 angle_start=0.0, angle_end=TAU, major_segments=72, minor_segments=10,
                 center_y=0.0, center_z=0.0):
    vertices = []
    for i in range(major_segments + 1):
        a = angle_start + (angle_end - angle_start) * i / major_segments
        for j in range(minor_segments):
            b = TAU * j / minor_segments
            vertices.append((x + tube_radius * math.sin(b),
                             center_y + (radius + tube_radius * math.cos(b)) * math.cos(a),
                             center_z + (radius + tube_radius * math.cos(b)) * math.sin(a)))
    faces = []
    for i in range(major_segments):
        for j in range(minor_segments):
            a = i * minor_segments + j
            b = i * minor_segments + (j + 1) % minor_segments
            c = (i + 1) * minor_segments + (j + 1) % minor_segments
            d = (i + 1) * minor_segments + j
            faces.append((a, b, c, d))
    return make_mesh(name, vertices, faces, mat, parent)


def make_shell_x(name, parent, x0, x1, inner0, outer0, inner1, outer1, mat,
                 *, angle_start=ANGLE_START, angle_end=ANGLE_END, segments=96):
    """Hollow casing sector with two open cutaway edges."""
    a0, a1 = math.radians(angle_start), math.radians(angle_end)
    vertices = []
    x_stations = (x0, x1)
    radii = ((outer0, outer1), (inner0, inner1))
    base = {}
    for surface, rs in enumerate(radii):
        for xi, (x, radius) in enumerate(zip(x_stations, rs)):
            key = (surface, xi)
            base[key] = len(vertices)
            for i in range(segments + 1):
                a = a0 + (a1 - a0) * i / segments
                vertices.append((x, radius * math.cos(a), radius * math.sin(a)))
    faces = []
    def idx(surface, xi, i):
        return base[(surface, xi)] + i
    for i in range(segments):
        faces.append((idx(0, 0, i), idx(0, 0, i + 1), idx(0, 1, i + 1), idx(0, 1, i)))
        faces.append((idx(1, 0, i + 1), idx(1, 0, i), idx(1, 1, i), idx(1, 1, i + 1)))
        faces.append((idx(0, 0, i), idx(1, 0, i), idx(1, 0, i + 1), idx(0, 0, i + 1)))
        faces.append((idx(0, 1, i + 1), idx(1, 1, i + 1), idx(1, 1, i), idx(0, 1, i)))
    for xi in (0, 1):
        faces.append((idx(0, xi, 0), idx(1, xi, 0), idx(1, xi, segments), idx(0, xi, segments)))
    return make_mesh(name, vertices, faces, mat, parent)


def make_blade_row(name, parent, x, count, root_radius, tip_radius, chord, mat,
                   *, lean=0.06, sweep=0.05, center_y=0.0, center_z=0.0,
                   envelope_mm=None, mass_kg=None, role=None, split_blades=False,
                   instance_label="blade", envelope_note=None,
                   reference_label=None, reference_envelope_mm=None,
                   reference_mass_kg=None, reference_note=None):
    """Create illustrative airfoils as one row mesh or individually selectable meshes."""
    vertices, faces = [], []
    stations = (-0.5, -0.18, 0.22, 0.5)
    thicknesses = (0.025, 0.16, 0.13, 0.018)

    def blade_props(instance_index):
        props = {"geometry_accuracy": "Illustrative airfoil proxy; not an OEM blade contour."}
        if envelope_mm:
            props["public_component_envelope_mm"] = envelope_mm
            props["envelope_source"] = BHEL_EOI
            props["envelope_note"] = envelope_note or (
                "Public casting envelope; the Blender proxy is not scaled to these dimensions."
            )
        if mass_kg is not None:
            props["public_component_mass_kg"] = mass_kg
        if role:
            props["row_role"] = role
        if reference_label:
            props["public_reference_label"] = reference_label
            props["public_reference_envelope_mm"] = reference_envelope_mm
            props["public_reference_mass_kg"] = reference_mass_kg
            props["reference_source"] = BHEL_EOI
            props["reference_note"] = reference_note or (
                "Stage-level public reference data; not dimensions or mass for this "
                "individual vane."
            )
        if split_blades:
            props["row_instance_index"] = instance_index + 1
            props["row_instance_count"] = count
            props["row_instance_count_note"] = (
                "Illustrative visual count; not a published 6B.03 blade count."
            )
        return props

    for blade in range(count):
        angle = TAU * blade / count
        blade_vertices = []
        blade_faces = []
        for radial_index, radius in enumerate((root_radius, tip_radius)):
            h = float(radial_index)
            for chord_index, station in enumerate(stations):
                thickness = chord * thicknesses[chord_index]
                camber = chord * 0.045 * math.sin(math.pi * chord_index / (len(stations) - 1))
                x_here = x + chord * station + lean * h
                radial_here = radius + sweep * math.sin(math.pi * chord_index / (len(stations) - 1))
                for side in (-1.0, 1.0):
                    tangent = camber + side * thickness
                    blade_vertices.append(
                        (
                            x_here,
                            center_y + radial_here * math.cos(angle) - tangent * math.sin(angle),
                            center_z + radial_here * math.sin(angle) + tangent * math.cos(angle),
                        )
                    )
        def vid(radial_layer, chord_index, side):
            return radial_layer * 8 + chord_index * 2 + side
        # Pressure and suction faces run from root to tip.
        for side in (0, 1):
            for k in range(3):
                blade_faces.append((vid(0, k, side), vid(0, k + 1, side),
                                    vid(1, k + 1, side), vid(1, k, side)))
        # Leading/trailing edges close the airfoil span.
        for edge in (0, 3):
            blade_faces.append((vid(0, edge, 0), vid(0, edge, 1),
                                vid(1, edge, 1), vid(1, edge, 0)))
        # Root and tip caps close the chord section.
        for radial_layer in (0, 1):
            for k in range(3):
                blade_faces.append((vid(radial_layer, k, 0), vid(radial_layer, k + 1, 0),
                                    vid(radial_layer, k + 1, 1), vid(radial_layer, k, 1)))
        if split_blades:
            blade_name = f"{name} | {instance_label} {blade + 1:02d} of {count}"
            make_mesh(blade_name, blade_vertices, blade_faces, mat, parent,
                      props=blade_props(blade))
        else:
            start = len(vertices)
            vertices.extend(blade_vertices)
            faces.extend(tuple(index + start for index in face) for face in blade_faces)
    if split_blades:
        return None
    props = blade_props(0)
    return make_mesh(name, vertices, faces, mat, parent, props=props)


def make_tube_z(name, parent, x, y, z0, z1, outer0, outer1, inner0, inner1, mat):
    segs = 64
    angles = [TAU * i / segs for i in range(segs)]
    verts = []
    for z, radius in ((z0, outer0), (z1, outer1), (z0, inner0), (z1, inner1)):
        verts.extend((x + radius * math.cos(a), y + radius * math.sin(a), z) for a in angles)
    bases = (0, segs, 2 * segs, 3 * segs)
    faces = []
    for i in range(segs):
        j = (i + 1) % segs
        faces.extend(((i, j, segs + j, segs + i),
                      (2 * segs + j, 2 * segs + i, 3 * segs + i, 3 * segs + j),
                      (i, 2 * segs + i, 2 * segs + j, j),
                      (segs + j, 3 * segs + j, 3 * segs + i, segs + i)))
    return make_mesh(name, verts, faces, mat, parent)


def make_box(name, parent, center, dimensions, mat):
    x, y, z = center
    dx, dy, dz = (value / 2.0 for value in dimensions)
    vertices = [(x + sx * dx, y + sy * dy, z + sz * dz)
                for sx, sy, sz in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                                   (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return make_mesh(name, vertices, faces, mat, parent, smooth=False)


def add_component(name, component_id, description, source_note):
    root = empty(f"{component_id} | {name}", component_id)
    root["reference_model"] = "GE Vernova 6B.03 family reference"
    root["geometry_accuracy"] = "Conceptual visualization; overall geometry is not dimensionally scaled."
    root["description"] = description
    root["source_note"] = source_note
    COMPONENT_ROOTS[component_id] = root
    return root


def build_inlet():
    root = add_component("Inlet and inlet guide vane section", "inlet",
                         "Short axial intake bellmouth and representative inlet guide vane row.",
                         "Inlet outline is a visual proxy; no public 6B.03 intake GA used.")
    make_tube_x("Intake bellmouth", root, -5.25, -4.2, 0.52, 0.83,
                r_inner0=0.44, r_inner1=0.75, mat=MATERIALS["casing"])
    make_torus_x("Bellmouth rolled lip", root, -5.25, 0.52, 0.055, MATERIALS["casing_light"])
    make_torus_x("Intake flange", root, -4.22, 0.83, 0.045, MATERIALS["casing_light"])
    make_blade_row("Inlet guide vanes | representative", root, -4.11, 28,
                   0.24, 0.76, 0.18, MATERIALS["rotor"], role="Illustrative IGV row")
    make_tube_x("Inlet hub", root, -4.24, -3.98, 0.24, 0.26,
                mat=MATERIALS["dark"])


def build_compressor():
    root = add_component("17-stage axial compressor", "compressor",
                         "Seventeen stage locations with alternating representative rotor/stator airfoil rows.",
                         "Stage count follows GE's public MS6001B family technical paper; exact 6B.03 row contours and assembly dimensions are not claimed.")
    root["published_architecture"] = "17-stage axial-flow compressor (MS6001B family reference)"
    root["published_architecture_source"] = GE_UPRATE
    x0, x1, stages = -4.02, -0.12, 17
    make_tube_x("Compressor rotor core", root, x0, x1, 0.24, 0.43,
                mat=MATERIALS["dark"])
    make_shell_x("Compressor casing | open cutaway", root, x0, x1,
                 0.88, 1.06, 1.04, 1.22, MATERIALS["casing"])
    for i in range(10):
        x = x0 + 0.16 + (x1 - x0 - 0.32) * i / 9
        radius = 1.06 + 0.16 * (x - x0) / (x1 - x0)
        make_torus_x(f"Casing stiffener {i + 1:02d}", root, x, radius, 0.036,
                     MATERIALS["casing_light"], angle_start=math.radians(ANGLE_START),
                     angle_end=math.radians(ANGLE_END))
    for edge, x in (("front", x0), ("aft", x1)):
        radius = 1.06 if edge == "front" else 1.22
        make_torus_x(f"Compressor split casing flange | {edge}", root, x, radius, 0.055,
                     MATERIALS["casing_light"], angle_start=math.radians(ANGLE_START),
                     angle_end=math.radians(ANGLE_END))
    pitch = (x1 - x0) / stages
    for stage in range(stages):
        f = (stage + 0.5) / stages
        hub = 0.25 + 0.18 * f
        tip = 0.70 + 0.30 * f
        center = x0 + (stage + 0.5) * pitch
        root["visual_stage_count"] = stages
        make_blade_row(f"Compressor rotor | stage {stage + 1:02d}", root,
                       center - 0.045, 26, hub, tip, 0.20 - 0.065 * f,
                       MATERIALS["rotor"], lean=0.045, sweep=0.025,
                       role="Rotor blade proxy; count and contour illustrative")
        make_blade_row(f"Compressor stator | stage {stage + 1:02d}", root,
                       center + 0.055, 30, hub + 0.02, tip - 0.012,
                       0.19 - 0.06 * f, MATERIALS["stator"], lean=-0.025,
                       sweep=-0.018, role="Stator vane proxy; count and contour illustrative")
        make_torus_x(f"Compressor rotor disk rim | {stage + 1:02d}", root,
                     center - 0.045, hub + 0.015, 0.022, MATERIALS["casing_light"],
                     major_segments=48, minor_segments=8)


def build_combustor():
    root = add_component("Reverse-flow can combustor", "combustor",
                         "Ten circumferentially arranged can proxies with liners and simplified transition pieces.",
                         "Ten reverse-flow chambers are documented for MS6001A/B in GE GER-4217B; this is family architecture, not a unit-specific 6B.03 drawing.")
    root["published_architecture"] = "10 reverse-flow chambers (MS6001 A/B family reference)"
    root["published_architecture_source"] = GE_UPRATE
    root["can_count"] = 10
    make_shell_x("Combustion wrapper | sectioned", root, -0.76, 0.82,
                 1.13, 1.24, 1.13, 1.26, MATERIALS["dark"],
                 angle_start=ANGLE_START, angle_end=ANGLE_END, segments=64)
    make_torus_x("Combustion wrapper forward flange", root, -0.74, 1.24, 0.05,
                 MATERIALS["casing_light"], angle_start=math.radians(ANGLE_START),
                 angle_end=math.radians(ANGLE_END))
    for can in range(10):
        a = TAU * can / 10.0
        cy, cz = 1.39 * math.cos(a), 1.39 * math.sin(a)
        label = f"Can {can + 1:02d}"
        make_tube_x(f"Combustion casing | {label}", root, -0.43, 0.66,
                    0.17, 0.15, r_inner0=0.12, r_inner1=0.105,
                    center_y=cy, center_z=cz, mat=MATERIALS["hot"])
        make_tube_x(f"Combustion liner | {label}", root, -0.24, 0.47,
                    0.102, 0.084, center_y=cy, center_z=cz,
                    mat=MATERIALS["hot_light"])
        make_torus_x(f"Can inlet collar | {label}", root, -0.41, 0.17, 0.022,
                     MATERIALS["casing_light"], center_y=cy, center_z=cz,
                     major_segments=24, minor_segments=8)
        make_torus_x(f"Can outlet collar | {label}", root, 0.65, 0.15, 0.02,
                     MATERIALS["casing_light"], center_y=cy, center_z=cz,
                     major_segments=24, minor_segments=8)
        # A tapered transition proxy turns each can toward the turbine entry.
        angle = a
        verts, faces = [], []
        rings = ((0.63, 1.39, 0.12), (0.94, 1.08, 0.085), (1.17, 0.77, 0.065))
        segs = 20
        for x, radius_from_axis, tube_r in rings:
            cc_y, cc_z = radius_from_axis * math.cos(angle), radius_from_axis * math.sin(angle)
            for j in range(segs):
                b = TAU * j / segs
                verts.append((x, cc_y + tube_r * math.cos(b), cc_z + tube_r * math.sin(b)))
        for k in range(len(rings) - 1):
            for j in range(segs):
                j2 = (j + 1) % segs
                faces.append((k * segs + j, k * segs + j2,
                              (k + 1) * segs + j2, (k + 1) * segs + j))
        transition = make_mesh(f"Transition piece proxy | {label}", verts, faces,
                               MATERIALS["hot_light"], root)
        transition["geometry_accuracy"] = "Swept conceptual surface; no OEM contour or dimensions asserted."
    make_tube_x("Fuel manifold ring | schematic", root, -0.23, -0.14,
                1.56, 1.56, r_inner0=1.50, r_inner1=1.50,
                mat=MATERIALS["accent"], segments=72)


def build_turbine():
    root = add_component("Three-stage axial turbine", "turbine",
                         "Three nozzle/bucket stage pairs and an open casing cutaway; blade shapes are visual proxies.",
                         "Three 6B.03 nozzle/bucket stages are listed in BHEL's public EOI. Their published component bounding dimensions are stored on the stage meshes.")
    root["published_architecture"] = "Three nozzle and bucket stages"
    root["published_architecture_sources"] = f"{BHEL_EOI} | {GE_UPRATE}"
    root["exhaust_layout_note"] = "Exhaust outlet layout is schematic; no public assembly drawing or package envelope dimensions found."
    x0, x1 = 1.15, 3.55
    make_shell_x("Turbine casing | open cutaway", root, x0, x1,
                 0.91, 1.10, 0.96, 1.21, MATERIALS["casing"])
    for i, (x, radius) in enumerate(((1.18, 1.10), (1.82, 1.13), (2.48, 1.17), (3.12, 1.20), (3.53, 1.21))):
        make_torus_x(f"Turbine casing rib {i + 1}", root, x, radius, 0.042,
                     MATERIALS["casing_light"], angle_start=math.radians(ANGLE_START),
                     angle_end=math.radians(ANGLE_END))
    make_tube_x("Turbine rotor drum", root, 1.18, 3.48, 0.36, 0.48,
                mat=MATERIALS["dark"])
    nozzle_envelopes = ((357, 208, 153), (361, 280, 170), (440, 353, 170))
    bucket_envelopes = ((267, 124, 52), (324, 124, 78), (394, 115, 82))
    nozzle_masses = (9.5, 19.0, 20.0)
    bucket_masses = (2.8, 3.1, 2.6)
    for stage in range(3):
        frac = stage / 2
        nozzle_x = 1.46 + stage * 0.69
        rotor_x = nozzle_x + 0.28
        hub = 0.39 + 0.08 * frac
        tip = 0.84 + 0.11 * frac
        nozzle_text = " x ".join(map(str, nozzle_envelopes[stage]))
        bucket_text = " x ".join(map(str, bucket_envelopes[stage]))
        make_blade_row(f"Stage {stage + 1} nozzle guide vanes", root,
                       nozzle_x, 26 - 2 * stage, hub + 0.03, tip,
                       0.30 - 0.045 * frac, MATERIALS["stator"], lean=-0.03,
                       sweep=-0.035, split_blades=True, instance_label="nozzle vane proxy",
                       role=f"Illustrative stage {stage + 1} nozzle-vane proxy",
                       reference_label=f"6B.03 stage {stage + 1} nozzle casting - BHEL EOI",
                       reference_envelope_mm=nozzle_text,
                       reference_mass_kg=nozzle_masses[stage],
                       reference_note=(
                           "BHEL lists these dimensions and mass for the stage nozzle casting item. "
                           "This selected mesh is one illustrative vane proxy; the listed values are "
                           "not for an individual vane. No single-vane contour or dimensions are "
                           "asserted, and the vane-row count is illustrative."
                       ))
        make_blade_row(f"Stage {stage + 1} rotating buckets", root,
                       rotor_x, 24 - 2 * stage, hub, tip - 0.035,
                       0.34 - 0.06 * frac, MATERIALS["hot_light"], lean=0.06,
                       sweep=0.045, envelope_mm=bucket_text,
                       envelope_note=(
                           "BHEL Annexure 1 lists this envelope and mass for one bucket casting. "
                           "This individual blade shape is an illustrative proxy and is not scaled "
                           "to the published envelope."
                       ),
                       mass_kg=bucket_masses[stage], split_blades=True,
                       instance_label="bucket casting proxy",
                       role=f"Illustrative stage {stage + 1} bucket-casting proxy")
        make_tube_x(f"Stage {stage + 1} rotor wheel", root,
                    rotor_x - 0.055, rotor_x + 0.055, hub - 0.02, hub + 0.01,
                    mat=MATERIALS["hot"])
        make_torus_x(f"Stage {stage + 1} shroud segment", root, rotor_x,
                     tip - 0.005, 0.035, MATERIALS["casing_light"],
                     angle_start=math.radians(ANGLE_START), angle_end=math.radians(ANGLE_END))
    # Schematic lower exhaust outlet, branching from the turbine casing.
    make_tube_z("Exhaust outlet diffuser | schematic", root, 3.17, 0.0,
                -2.05, -0.88, 0.42, 0.31, 0.33, 0.23,
                MATERIALS["casing"])
    make_tube_z("Exhaust outlet inner liner | schematic", root, 3.17, 0.0,
                -2.02, -0.89, 0.32, 0.22, 0.29, 0.19,
                MATERIALS["hot"])


def build_shaft():
    root = add_component("Single-shaft rotor line", "shaft",
                         "Continuous axial shaft representation with bearing journals and load coupling.",
                         "Single-shaft architecture is documented in GE GER-4217B for the MS6001 family; visual lengths and diameters are not sourced dimensions.")
    root["published_architecture"] = "Single shaft, two-bearing MS6001 family reference"
    root["published_architecture_source"] = GE_UPRATE
    make_tube_x("Main rotor shaft", root, -4.42, 4.35, 0.125, 0.14,
                mat=MATERIALS["rotor"])
    for label, x, radius in (("front bearing journal", -3.68, 0.19),
                             ("compressor aft journal", -0.09, 0.22),
                             ("turbine aft journal", 3.42, 0.23),
                             ("load coupling", 4.17, 0.29)):
        make_tube_x(label, root, x - 0.11, x + 0.11, radius, radius,
                    mat=MATERIALS["casing_light"])
        make_torus_x(label + " shoulder", root, x, radius, 0.022,
                     MATERIALS["hot_light"] if "coupling" in label else MATERIALS["rotor"])


def build_generator():
    root = add_component("Load gear and generator", "generator",
                         "Illustrative speed-reduction gear housing, coupling, generator shell, fins, and terminal box.",
                         "GE's 6B.03 public catalog identifies the 50/60 Hz models as geared; package-specific gearbox and generator geometry is not claimed.")
    root["published_configuration"] = "50/60 Hz geared configuration"
    root["published_configuration_source"] = GE_CATALOG
    make_tube_x("Load gear casing", root, 4.12, 4.95, 0.60, 0.63,
                r_inner0=0.0, mat=MATERIALS["casing"])
    for i in range(5):
        x = 4.18 + i * 0.17
        make_torus_x(f"Gear casing rib {i + 1}", root, x, 0.61 + i * 0.004,
                     0.026, MATERIALS["casing_light"], major_segments=48)
    make_tube_x("Generator frame", root, 4.96, 6.58, 0.71, 0.71,
                r_inner0=0.0, mat=MATERIALS["casing"])
    make_tube_x("Generator end bell", root, 6.52, 6.73, 0.73, 0.63,
                mat=MATERIALS["casing_light"])
    make_tube_x("Generator shaft cap", root, 6.70, 6.83, 0.30, 0.30,
                mat=MATERIALS["dark"])
    for i in range(12):
        x = 5.10 + i * 0.12
        make_torus_x(f"Generator cooling fin {i + 1:02d}", root, x, 0.715,
                     0.018, MATERIALS["casing_light"], major_segments=48, minor_segments=8)
    make_box("Generator terminal box", root, (5.70, 0.0, 0.86), (0.78, 0.64, 0.44), MATERIALS["casing"])
    make_box("Terminal cover", root, (5.70, 0.0, 1.09), (0.72, 0.59, 0.055), MATERIALS["casing_light"])
    for y in (-0.34, 0.34):
        make_box(f"Generator support foot {y:+.2f}", root, (5.75, y, -0.78), (0.72, 0.18, 0.34), MATERIALS["casing"])


def build_presentation():
    # Presentation-only floor, lights, and camera. They are not included in GLB.
    floor_mesh = bpy.data.meshes.new("Presentation floor | mesh")
    floor_mesh.from_pydata([(-20, -20, -2.25), (20, -20, -2.25),
                            (20, 20, -2.25), (-20, 20, -2.25)], [], [(0, 1, 2, 3)])
    floor_mesh.materials.append(MATERIALS["ground"])
    floor = bpy.data.objects.new("Presentation floor | not exported", floor_mesh)
    link_object(floor, collection=PRESENTATION_COLLECTION, model=False)

    def point_at(obj, target):
        obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()

    camera_data = bpy.data.cameras.new("Hero camera")
    camera = bpy.data.objects.new("Hero camera | not exported", camera_data)
    link_object(camera, collection=PRESENTATION_COLLECTION, model=False)
    camera.location = (-11.0, -12.5, 9.3)
    camera_data.lens = 52
    point_at(camera, (0.45, 0.0, -0.1))
    bpy.context.scene.camera = camera

    def add_area(name, location, energy, color, size, target):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.color = color
        data.shape = "DISK"
        data.size = size
        obj = bpy.data.objects.new(name + " | not exported", data)
        link_object(obj, collection=PRESENTATION_COLLECTION, model=False)
        obj.location = location
        point_at(obj, target)

    add_area("Key | cool softbox", (1, 6, 8), 2800, (0.75, 0.88, 1.0), 8, (0, 0, 0))
    add_area("Rim | warm", (-5, -4, 4), 2200, (1.0, 0.48, 0.23), 6, (0, 0, 0))
    add_area("Fill | frontal", (4, 8, 2.5), 1700, (0.35, 0.8, 0.9), 7, (0, 0, 0))
    add_area("Generator edge", (7, -1, 6), 1100, (0.82, 0.9, 0.92), 5, (5, 0, 0))


def set_scene_and_metadata():
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene["reference_model"] = "GE Vernova 6B.03 | public-data reference visualization"
    scene["assembly_dimensions"] = "Not to scale. No public 6B.03 general-arrangement drawing located."
    scene["geometry_provenance"] = "Conceptual visualization authored from public architecture and selected published part-envelope facts."
    scene["performance_source"] = GE_CATALOG
    scene["simple_cycle_net_output_mw"] = 45.0
    scene["simple_cycle_net_efficiency_lhv"] = 0.334
    scene["simple_cycle_net_heat_rate_btu_per_kwh_lhv"] = 10216.0
    scene["simple_cycle_net_heat_rate_kj_per_kwh_lhv"] = 10779.0
    scene["compression_pressure_ratio"] = 12.8
    scene["exhaust_temperature_c"] = 561.0
    scene["exhaust_mass_flow_kg_s"] = 145.1
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 950
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("TurbineIQ midnight studio")
    scene.world.color = (0.018, 0.027, 0.04)
    scene.world.use_nodes = True
    scene.world.node_tree.nodes.get("Background").inputs["Color"].default_value = (0.018, 0.027, 0.04, 1.0)
    scene.view_settings.view_transform = "AgX"
    scene.camera.data.lens = 52
    scene.render.filepath = str(PREVIEW_PATH)
    scene.render.image_settings.color_mode = "RGBA"
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"


def export_glb():
    GLB_PATH.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in MODEL_OBJECTS:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = ASSET_ROOT
    bpy.ops.export_scene.gltf(
        filepath=str(GLB_PATH),
        export_format="GLB",
        use_selection=True,
        export_extras=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
    )
    bpy.ops.object.select_all(action="DESELECT")


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    global MODEL_COLLECTION, PRESENTATION_COLLECTION, ASSET_ROOT
    create_materials()
    MODEL_COLLECTION = bpy.data.collections.new("TurbineIQ | interactive turbine asset")
    PRESENTATION_COLLECTION = bpy.data.collections.new("Presentation | render-only")
    bpy.context.scene.collection.children.link(MODEL_COLLECTION)
    bpy.context.scene.collection.children.link(PRESENTATION_COLLECTION)
    ASSET_ROOT = bpy.data.objects.new("GE 6B.03 reference | visual model, not to scale", None)
    ASSET_ROOT["reference_model"] = "GE Vernova 6B.03"
    ASSET_ROOT["geometry_accuracy"] = "Conceptual; no OEM assembly drawing, CAD, or overall dimensions reproduced."
    ASSET_ROOT["public_sources"] = f"{GE_CATALOG} | {GE_UPRATE} | {BHEL_EOI}"
    link_object(ASSET_ROOT)

    build_inlet()
    build_compressor()
    build_combustor()
    build_turbine()
    build_shaft()
    build_generator()

    # Visible twin-support rails are separated from the six selectable groups.
    rails = empty("Support skid | visual context")
    rails["geometry_accuracy"] = "Illustrative support geometry only."
    for y in (-0.52, 0.52):
        make_box(f"Longitudinal skid rail {y:+.2f}", rails, (0.55, y, -1.65), (10.7, 0.22, 0.26), MATERIALS["casing"])
        for x in (-3.45, -0.25, 2.8, 5.55):
            make_box(f"Skid cross support {x:+.2f} {y:+.2f}", rails,
                     (x, y, -1.44), (0.46, 0.34, 0.32), MATERIALS["casing_light"])
    build_presentation()
    set_scene_and_metadata()

    # Save a full editable Blender scene, then export only the interactive model.
    BLEND_PATH.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    export_glb()
    bpy.context.scene.render.filepath = str(PREVIEW_PATH)
    bpy.ops.render.render(write_still=True)
    print(f"BUILT_BLEND={BLEND_PATH}")
    print(f"BUILT_GLB={GLB_PATH}")
    print(f"BUILT_PREVIEW={PREVIEW_PATH}")
    print(f"MODEL_OBJECTS={len(MODEL_OBJECTS)}")
    print(f"COMPONENT_ROOTS={','.join(sorted(COMPONENT_ROOTS))}")


if __name__ == "__main__":
    main()
