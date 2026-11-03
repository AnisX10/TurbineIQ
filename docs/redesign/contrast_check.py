#!/usr/bin/env python3
"""Check the locked TurbineIQ light/dark token contrast pairs."""

from __future__ import annotations


def luminance(hex_color: str) -> float:
    values = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


THEMES = {
    "light": {
        "surface": "#ffffff", "ground": "#f2f4f7", "text": "#0a0a0a",
        "muted": "#6b6b6b", "chart-3": "#1d5fbf", "accent": "#141414",
        "pills": {
            "positive": ("#04250e", "#dcfae5"),
            "negative": ("#831c1e", "#ffedea"),
            "warning": ("#92400e", "#fffbeb"),
            "neutral": ("#3d3d3d", "#eeeeee"),
        },
    },
    "dark": {
        "surface": "#141518", "ground": "#0e0f11", "text": "#f2f3f4",
        "muted": "#9a9ea5", "chart-3": "#6ea2f0", "accent": "#f2f3f4",
        "pills": {
            "positive": ("#5fc39c", "#1b2828"),
            "negative": ("#ef6b7a", "#2c1a20"),
            "warning": ("#d9a441", "#2a2416"),
            "neutral": ("#c9ccd1", "#212226"),
        },
    },
}

failed = False
print("theme | pair | contrast | minimum | result")
for theme, t in THEMES.items():
    checks = [
        ("--text on --surface", t["text"], t["surface"], 4.5),
        ("--text on --ground", t["text"], t["ground"], 4.5),
        ("--muted on --surface", t["muted"], t["surface"], 4.5),
        ("--muted on --ground", t["muted"], t["ground"], 4.5),
        ("--chart-3 on --surface", t["chart-3"], t["surface"], 3.0),
        ("--accent on --surface", t["accent"], t["surface"], 3.0),
    ]
    checks.extend(
        (f"{name} pill ink on background", ink, background, 4.5)
        for name, (ink, background) in t["pills"].items()
    )
    for name, fg, bg, minimum in checks:
        value = ratio(fg, bg)
        passed = value >= minimum
        failed |= not passed
        print(f"{theme} | {name} | {value:.2f}:1 | {minimum:.1f}:1 | {'PASS' if passed else 'FAIL'}")
if failed:
    raise SystemExit(1)
