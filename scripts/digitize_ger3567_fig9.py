"""Digitize GER-3567H Figure 9 (effect of ambient temperature, single-shaft MS7001).

Reads the rendered page by colour: output (green), heat rate (orange), exhaust flow
(yellow dots). Axes are calibrated from the plot frame (0 to 120 F, 70 to 130 percent of
design). Values are normalised to 100 at the 59 F / 15 C ISO point and compared with the
calibrated model's ambient sweep. Reading error is about +/-0.4 percentage points (line
width of about 4 px at 8.5 px per percentage point).

Usage:
    pdftoppm -r 250 -f 12 -l 12 -png GER-3567H.pdf amb
    python scripts/digitize_ger3567_fig9.py amb-12.png docs/evidence/calibration/ger3567_fig9.json
(requires pillow and numpy.) The PDF is a copyrighted GE document and is not committed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from turbineiq.engineering.real_gas import CALIBRATED_6B03, at_ambient, simulate_real_gas_cycle

FRAME_SCALE = 1.37  # rendered at 250 dpi


def _frame(im: np.ndarray) -> tuple[float, float, float, float]:
    y0, y1 = int(1230 * FRAME_SCALE), int(1650 * FRAME_SCALE)
    x0, x1 = int(500 * FRAME_SCALE), int(1050 * FRAME_SCALE)
    sub = im[y0:y1, x0:x1]
    dark = sub.sum(axis=2) < 150
    rows = [i + y0 for i, v in enumerate(dark.sum(axis=1)) if v > 0.48 * sub.shape[1]]
    cols = [i + x0 for i, v in enumerate(dark.sum(axis=0)) if v > 0.48 * sub.shape[0]]
    # top frame line, bottom axis line, left and right frame lines
    return float(cols[0] + 0.5), float(cols[-1]), float(rows[3]) - 0.5, float(rows[-1])


def main(image: Path, out: Path) -> None:
    im = np.array(Image.open(image).convert("RGB")).astype(int)
    xl, xr, yt, yb = _frame(im)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    masks = {
        "output": (g > 200) & (r < 100) & (b < 100),
        "heat_rate": (r > 200) & (g > 50) & (g < 130) & (b < 90),
        "exhaust_flow": (r > 150) & (g > 150) & (b < 90),
    }

    def pct(y: float) -> float:
        return 130 - (y - yt) / (yb - yt) * 60

    curves: dict[str, list[tuple[float, float]]] = {}
    for name, mask in masks.items():
        pts = []
        for f in range(0, 120, 5):
            x = int(round(xl + f / 120 * (xr - xl)))
            ys: list[int] = []
            for dx in (-2, -1, 0, 1, 2):
                col = mask[int(yt) - 5 : int(yb) + 5, x + dx]
                ys += list(np.where(col)[0] + int(yt) - 5)
            if ys:
                pts.append((float(f), pct(float(np.mean(ys)))))
        curves[name] = pts

    def at_f(name: str, f: float) -> float:
        xs, ys = zip(*curves[name], strict=True)
        # linear fit: the published curves are straight lines
        slope, icpt = np.polyfit(xs, ys, 1)
        return float(slope * f + icpt)

    iso_f = 59.0
    rows = []
    for t_c in (0, 10, 15, 20, 25, 30, 35, 40, 45):
        f = t_c * 9 / 5 + 32
        model = simulate_real_gas_cycle(at_ambient(CALIBRATED_6B03, float(t_c)))
        iso = simulate_real_gas_cycle(CALIBRATED_6B03)
        rows.append(
            {
                "ambient_c": t_c,
                "ger_output_percent": at_f("output", f) / at_f("output", iso_f) * 100,
                "model_output_percent": model.net_electrical_power_mw
                / iso.net_electrical_power_mw
                * 100,
                "ger_heat_rate_percent": at_f("heat_rate", f) / at_f("heat_rate", iso_f) * 100,
                "model_heat_rate_percent": model.heat_rate_kj_per_kwh
                / iso.heat_rate_kj_per_kwh
                * 100,
                "ger_exhaust_flow_percent": at_f("exhaust_flow", f)
                / at_f("exhaust_flow", iso_f)
                * 100,
                "model_exhaust_flow_percent": model.exhaust_mass_flow_kg_s
                / iso.exhaust_mass_flow_kg_s
                * 100,
            }
        )
    out.write_text(
        json.dumps(
            {
                "frame_px": {"x_left": xl, "x_right": xr, "y_top": yt, "y_bottom": yb},
                "reading_error_percentage_points": 0.4,
                "comparison": rows,
            },
            indent=2,
        )
        + "\n"
    )
    for row in rows:
        print(
            f"{row['ambient_c']:>3} C  output GER {row['ger_output_percent']:6.1f} "
            f"model {row['model_output_percent']:6.1f} | "
            f"HR GER {row['ger_heat_rate_percent']:6.1f} "
            f"model {row['model_heat_rate_percent']:6.1f} | flow GER "
            f"{row['ger_exhaust_flow_percent']:6.1f} model {row['model_exhaust_flow_percent']:6.1f}"
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
